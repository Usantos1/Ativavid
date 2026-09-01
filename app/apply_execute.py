"""Executa o plano de Aplicar alterações. Sem Whisper, sem LLM, sem recorte por IA.

O planner (apply_plan.py) continua puro. Daqui para baixo é orquestração do
pipeline já existente: render.py para corte, overlay/Remotion para o visual,
delivery_pack para a pasta publicar.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.apply_plan import DIRTY_KEYS, empty_dirty, plan_apply_changes
from app.caption_remap import (
    OVERLAP_FAIL,
    attach_provenance_from_transcripts,
    provenance_error,
    remap_captions_between_timelines,
    retime_captions_for_edl,
    validate_remapped_captions,
)
from app.quick_corrections import (
    captions_path,
    edit_data_path,
    edl_path,
    load,
    read_edl_ranges,
    save,
    _jcut_snapshot,
    _ranges_snapshot,
)
from app.timeline_map import (
    build_timeline_map,
    map_output_duration,
    read_mp4_video_frames,
    validate_timeline_map,
)

TMP_CUT = "cut.apply.tmp.mp4"
TMP_FINAL = "final.apply.tmp.mp4"
TMP_CAPTIONS = "captions.apply.json"
APPLY_STATUS = "apply_status.json"
APPLY_HISTORY = "apply_history.json"
APPLY_HISTORY_MAX = 80
MIN_FINAL_BYTES = 12_000
# Cada motivo conhecido vira UMA frase com o proximo passo. Sem isto o
# usuario lia sempre a mesma linha generica (14 de 99 aplicacoes falharam no
# historico dele) e o motivo tecnico ficava num campo que a tela nem mostra.
#
# A chave e um pedaco do erro interno; a primeira que casar vence.
MOTIVOS_DO_APPLY: tuple[tuple[str, str], ...] = (
    ("ordem das palavras",
     "As legendas não casaram com o corte novo. Use "
     "“Salvar e refazer a Fase 2” para recriá-las a partir do corte atual "
     "— as suas correções de texto são mantidas."),
    ("token duplicado",
     "As legendas não casaram com o corte novo (uma palavra aparece duas "
     "vezes). Use “Salvar e refazer a Fase 2” para recriá-las."),
    ("OLD map",
     "O corte que está no disco não é o que a tela mostra — ele deve ter "
     "sido refeito por fora. Recarregue o projeto e tente de novo."),
    ("o mapa previa",
     "O corte saiu com um tamanho diferente do previsto e nada foi "
     "alterado. Tente de novo; se repetir, use “Salvar e refazer a Fase 2”."),
    ("fila cheia",
     "Outro vídeo está sendo processado agora. Tente de novo quando a fila "
     "esvaziar."),
    ("timestamp fora da duração",
     "Uma legenda aponta para um instante que não existe mais no corte. "
     "Use “Salvar e refazer a Fase 2” para recriá-las."),
    # PermissionError do Windows quando o video esta aberto em outro
    # programa — a mensagem generica escondia um conserto de 2 segundos.
    ("winerror 32",
     "O vídeo está aberto em outro programa (player ou pasta com "
     "pré-visualização). Feche-o e clique em Aplicar de novo."),
)


def motivo_do_apply(erro: str | None) -> str | None:
    """A frase em portugues para um erro interno conhecido, ou None."""
    t = str(erro or "").lower()
    for chave, frase in MOTIVOS_DO_APPLY:
        if chave.lower() in t:
            return frase
    return None


FAIL_MSG = "Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido."
PREPARE_FAIL_MSG = "Não foi possível preparar este corte. O vídeo anterior foi mantido."
PROVENANCE_FAIL_MSG = "Este projeto antigo precisa ser atualizado antes de aplicar cortes manuais."

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, str], None]


class ApplyError(RuntimeError):
    """Falha controlada: o final anterior deve permanecer intacto."""


class PrepareError(ApplyError):
    """Invariante do EDL/remap falhou antes de qualquer render."""

    def __init__(self, detail: str, user_message: str | None = None):
        super().__init__(detail)
        self.user_message = user_message or PREPARE_FAIL_MSG


@dataclass
class ApplyHooks:
    """Passos de mídia injetáveis. Testes usam mocks; produção usa default_hooks()."""

    rebuild_cut: Callable[[Path, Path], Path]
    render_visual: Callable[..., Path]
    validate_final: Callable[..., tuple[bool, dict[str, Any]]]
    promote_file: Callable[[Path, Path], None]
    sync_pack: Callable[[Path, Path], Path | None]
    probe_duration: Callable[[Path], float]
    log: LogFn
    progress: ProgressFn


# Qual motor desenhou o visual do ultimo apply, e por que caiu se caiu.
# O log do apply so vai para a tela (`_print_log`), entao o motivo de uma
# queda se perdia — foi exatamente por isso que deu para diagnosticar o
# desperdicio do RENDER (que grava `render-stats.json` e `canary-state.json`)
# e nao o do APPLY. Medido no historico do usuario: o mesmo tipo de apply
# variou de 1,2x a 31,3x o tempo real, e nao havia como saber qual foi qual.
# As duas metricas do apply, POR PROJETO. `is_apply_running` e por projeto
# (le o apply_status.json daquele edit), entao dois projetos diferentes rodam
# apply ao MESMO tempo, cada um na sua thread "quick-apply", no mesmo processo.
# Guardadas num dicionario unico elas se misturavam: o motor de um projeto ia
# parar no historico do outro, e os tempos por fase viravam a soma de dois
# applies. Como e justamente esta medicao que vai decidir o que otimizar, um
# numero misturado e pior do que numero nenhum.
_ULTIMO_MOTOR: dict[str, dict[str, str]] = {}
# Segundos por FASE. Os cronometros ja existiam — mas so no stdout do worker,
# que ninguem guarda. O historico registrava o total e mais nada, entao
# "demorou 9 minutos" nao dizia se o custo estava no desenho, no encode ou na
# validacao.
_FASES: dict[str, dict[str, float]] = {}
_METRICAS_LOCK = threading.Lock()


def _chave(edit_dir: Path) -> str:
    try:
        return str(Path(edit_dir).resolve()).lower()
    except OSError:
        return str(edit_dir).lower()


def _motor(edit_dir: Path, engine: str, motivo: str | None = None) -> None:
    with _METRICAS_LOCK:
        d = {"engine": engine}
        if motivo:
            d["fallbackReason"] = motivo[:160]
        _ULTIMO_MOTOR[_chave(edit_dir)] = d


def _fase(edit_dir: Path, nome: str, t0: float) -> float:
    """Marca a fase e devolve o que ela levou, para o log continuar igual."""
    dt = time.time() - t0
    with _METRICAS_LOCK:
        _FASES.setdefault(_chave(edit_dir), {})[nome] = round(dt, 3)
    return dt


def _colher(edit_dir: Path) -> dict[str, object]:
    """Tira as metricas deste projeto do mapa e devolve o que gravar."""
    k = _chave(edit_dir)
    with _METRICAS_LOCK:
        fases = _FASES.pop(k, {})
        motor = _ULTIMO_MOTOR.pop(k, {})
    saida: dict[str, object] = {k2: v for k2, v in motor.items() if v}
    if fases:
        saida["phases"] = fases
    return saida


def _print_log(line: str) -> None:
    print(line, flush=True)


# O log do apply so ia para a tela — e o apply roda DENTRO do app, cujo
# stdout no pacote (pythonw) nao vai a lugar nenhum. O comentario la em
# cima ja dizia o preco disso: deu para diagnosticar o desperdicio do
# RENDER, que grava arquivos, e nao o do APPLY, que so imprimia. Medido no
# historico do usuario, o mesmo tipo de apply variou de 1,2x a 31,3x o
# tempo real e nao havia como saber qual foi qual.
_APPLY_LOG_MAX = 200_000       # o arquivo cresce a cada apply do projeto


def _log_do_apply(edit_dir: Path):
    """Log que vai para a tela E para `edit/apply.log`."""
    alvo = Path(edit_dir) / "apply.log"

    def _log(line: str) -> None:
        print(line, flush=True)
        try:
            from app.app_log import scrub

            with alvo.open("a", encoding="utf-8") as fh:
                fh.write(scrub(str(line)) + chr(10))
            # Aparar so quando passa do teto: reescrever a cada linha
            # custaria um arquivo inteiro por linha de log.
            if alvo.stat().st_size > _APPLY_LOG_MAX * 1.5:
                texto = alvo.read_text(encoding="utf-8", errors="replace")
                alvo.write_text(texto[-_APPLY_LOG_MAX:], encoding="utf-8")
        except Exception:  # noqa: BLE001 — log e extra, o video e o produto
            pass

    return _log


def _default_progress(edit_dir: Path) -> ProgressFn:
    def progress(stage: str, message: str) -> None:
        write_apply_status(edit_dir, running=True, ok=None, message=message, stage=stage)
        try:
            from pipeline.run_fast import set_stage

            set_stage(edit_dir, stage, message, None)
        except Exception:
            pass

    return progress


def write_apply_status(edit_dir: Path, **fields: Any) -> dict[str, Any]:
    path = Path(edit_dir) / APPLY_STATUS
    cur: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                cur = loaded
        except (OSError, json.JSONDecodeError, TypeError):
            cur = {}
    cur.update(fields)
    cur.setdefault("running", False)
    # Carimbo SEMPRE renovado: o lock do apply expira por este campo, e o
    # update acima preservava um `at` de gravações antigas — um status recém
    # escrito podia nascer "vencido" (ou, pior, um velho parecer fresco).
    if "at" not in fields:
        import datetime as _dt

        cur["at"] = _dt.datetime.now().isoformat(timespec="seconds")
    tmp = path.with_suffix(path.suffix + ".tmp")
    last: OSError | None = None
    for attempt in range(8):
        try:
            tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
            last = None
            break
        except OSError as exc:
            last = exc
            time.sleep(0.04 * (attempt + 1))
    if last:
        raise last
    try:
        from app.apply_tasks import sync_from_status

        sync_from_status(Path(edit_dir), cur)
    except Exception:
        pass
    return cur


def read_apply_status(edit_dir: Path) -> dict[str, Any]:
    path = Path(edit_dir) / APPLY_STATUS
    if not path.exists():
        return {"running": False, "ok": None, "message": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"running": False, "ok": None, "message": ""}
    return data if isinstance(data, dict) else {"running": False}


def _status_vencido(carimbo: str, minutos: float) -> bool:
    """True se o carimbo é mais velho que N minutos (ou ilegível)."""
    import datetime as _dt

    raw = str(carimbo or "").replace("Z", "+00:00")
    try:
        t = _dt.datetime.fromisoformat(raw)
    except ValueError:
        return True  # sem carimbo legível o lock não se sustenta
    agora = _dt.datetime.now(t.tzinfo) if t.tzinfo else _dt.datetime.now()
    return (agora - t).total_seconds() > minutos * 60


def is_apply_running(edit_dir: Path) -> bool:
    """True se já está na fila ou executando — não abre segundo Apply.

    O lock EXPIRA. Caso real (21-25/08): um apply falhou, delegou o rerun ao
    pipeline (stage="queued", ok=None) e ninguém finalizou o status quando o
    pipeline terminou — o projeto respondeu "Já estou aplicando" por QUATRO
    DIAS a cada clique. Fila que não começou em 10 min está morta; execução
    com mais de 2h também (a mediana do apply é 15-35s; o rerun completo,
    minutos). Estado velho não segura lock — no pior caso um segundo apply
    roda, que é recuperável; um projeto travado para sempre não é.
    """
    st = read_apply_status(edit_dir)
    if st.get("running"):
        return not _status_vencido(str(st.get("at") or ""), 120)
    if st.get("ok") is None and str(st.get("stage") or "") == "queued":
        return not _status_vencido(str(st.get("at") or ""), 10)
    try:
        from app.apply_tasks import STATUS_QUEUED, STATUS_RUNNING, read_task

        task = read_task(edit_dir)
        if task and str(task.get("status") or "") in (STATUS_QUEUED, STATUS_RUNNING):
            carimbo = str(task.get("updatedAt") or task.get("startedAt") or "")
            prazo = 10 if str(task.get("status")) == STATUS_QUEUED else 120
            return not _status_vencido(carimbo, prazo)
    except Exception:
        pass
    return False


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def captions_timed_to(edit_dir: Path) -> list[dict]:
    """EDL contra o qual captions.json está cronometrado (cut atual)."""
    corr = load(edit_dir)
    timed = corr.get("captionsTimedTo")
    if isinstance(timed, list) and timed:
        return [r for r in timed if isinstance(r, dict)]
    return read_edl_ranges(edit_dir)


def _edit_fps(edit_dir: Path) -> float:
    corr = load(edit_dir)
    try:
        fps = float(corr.get("captionsTimedToFps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    if fps > 0:
        return fps
    data = _read_json(edit_data_path(edit_dir), {}) or {}
    edl = _read_json(edl_path(edit_dir), {}) or {}
    for src in (data, edl):
        if not isinstance(src, dict):
            continue
        for key in ("fps", "targetFps"):
            try:
                val = float(src.get(key) or 0)
            except (TypeError, ValueError):
                val = 0.0
            if val > 0:
                return val
    return 30.0


def _recover_timed_jcut(edit_dir: Path, timed: list[dict]) -> list | None:
    from app.quick_corrections import _same_ranges

    versions = Path(edit_dir) / "versions"
    if not versions.is_dir():
        return None
    files = sorted(versions.glob("v*.json"), reverse=True)
    for path in files:
        data = _read_json(path, {})
        if not isinstance(data, dict):
            continue
        edl = data.get("edl")
        if not isinstance(edl, dict):
            continue
        ranges = [r for r in (edl.get("ranges") or []) if isinstance(r, dict)]
        jt = edl.get("jcut_timeline")
        if isinstance(jt, list) and jt and _same_ranges(timed, ranges):
            return jt
    return None


def caption_timeline_edls(edit_dir: Path) -> tuple[dict, dict, float, list | None]:
    """EDL do cut atual (legendas) e EDL novo. Não adivinha source por segundo."""
    from app.quick_corrections import _same_ranges

    corr = load(edit_dir)
    timed = captions_timed_to(edit_dir)
    current = _read_json(edl_path(edit_dir), {}) or {}
    if not isinstance(current, dict):
        current = {"ranges": read_edl_ranges(edit_dir)}
    fps = _edit_fps(edit_dir)
    prior = corr.get("captionsTimedToJcut")
    if not isinstance(prior, list) or not prior:
        prior = _recover_timed_jcut(edit_dir, timed)
    old: dict[str, Any] = {
        "ranges": timed,
        "fps": fps,
        "sources": current.get("sources") if isinstance(current.get("sources"), dict) else {},
    }
    if prior:
        old["jcut_timeline"] = prior
    cfg = current.get("jcut")
    if cfg is False or cfg in ("off", "none"):
        old["jcut"] = False
    elif prior or current.get("total_duration_s"):
        old["jcut"] = True if cfg is None else cfg
        if current.get("total_duration_s") and not prior:
            old["total_duration_s"] = current["total_duration_s"]
    current_ranges = [r for r in (current.get("ranges") or []) if isinstance(r, dict)]
    if (
        not prior
        and isinstance(current.get("jcut_timeline"), list)
        and current.get("jcut_timeline")
        and _same_ranges(timed, current_ranges)
    ):
        old["jcut_timeline"] = current["jcut_timeline"]
        old["jcut"] = True if cfg is None else cfg
    return old, current, fps, prior


def pending_caption_remap(edit_dir: Path) -> list[dict] | None:
    """Remapeamento temporal derivado. Não grava captions.json.

    Texto corrigido em captions.json é a verdade. Só os timings mudam.
    None = EDL do cut e EDL atual são o mesmo — nada pendente.
    """
    from app.quick_corrections import _same_ranges

    old, new, fps, prior = caption_timeline_edls(edit_dir)
    current = [r for r in (new.get("ranges") or []) if isinstance(r, dict)]
    if not current or _same_ranges(old.get("ranges") or [], current):
        return None
    words = _read_json(captions_path(edit_dir), [])
    if not isinstance(words, list) or not words:
        return None
    return retime_captions_for_edl(words, old, new, fps=fps, prior_jcut=prior, edit_dir=edit_dir)


def expected_output_duration(edit_dir: Path) -> float:
    edl = _read_json(edl_path(edit_dir), {}) or {}
    if not isinstance(edl, dict):
        edl = {"ranges": read_edl_ranges(edit_dir)}
    corr = load(edit_dir)
    prior = corr.get("captionsTimedToJcut")
    if not isinstance(prior, list):
        prior = None
    return float(map_output_duration(build_timeline_map(edl, fps=_edit_fps(edit_dir), prior_jcut=prior)))


def tolerancia_de_quadros(n_ranges: int) -> int:
    """Quantos quadros o mapa pode divergir do corte sem isso ser defeito.

    O mapa soma `duracao * fps` por range; o corte e o que o ffmpeg entrega.
    Os dois nunca bateram: cada segmento sai 2 a 7 quadros mais curto que a
    duracao pedida (o `-ss` de entrada cai no keyframe anterior e descarta ate
    ali), e a emenda com J-cut compensa parte disso. O que sobra e uma deriva
    que ACOMPANHA o numero de emendas.

    Medido nos 128 projetos do usuario em 21/08/2026: a deriva vai de 0 a 21
    quadros e chega a **1,80 quadro por emenda** (9 quadros num projeto de 5
    ranges). Uma medicao anterior, com 39 projetos, viu no maximo 0,75 por
    emenda e a folga foi calibrada nisso — a amostra maior desmente: com
    `2 + 0,8n` esse projeto de 5 ranges era RECUSADO por 3 quadros.

    E a deriva nao cresce em linha com as emendas, cresce como RAIZ: 9 quadros
    com 5 emendas e 21 com 38. Um modelo linear generoso o bastante para o
    projeto de 5 daria 78 quadros de folga no de 38 — mais que um take inteiro
    de 2s, e a guarda pararia de pegar o que existe para pegar. Uma raiz
    acompanha as duas pontas com a mesma constante (3,1 sai de cada uma delas
    isolada; 5,0 e essa curva com margem de guarda).

    Contra os 128 projetos, comparado com o `2 + 0,8n` que estava aqui:

    | | 2+0,8n | 2+5,0*raiz(n) |
    |---|---|---|
    | projetos aceitos | 127/128 | **128/128** |
    | margem no mais apertado | -3 (recusa) | +4 |
    | folga com 38 emendas | 32 | 33 |
    | menor take que ainda pega | 1,1s | 1,1s |
    | mapa de OUTRO corte que passa | 3/128 | 3/128 |

    Ou seja: a recusa falsa some sem custar nada em deteccao. Os 3 que passam
    nos dois modelos sao projetos diferentes cuja contagem de quadros bate por
    coincidencia — a contagem nao separa esses, e quem os pega e outra rede
    (veja abaixo).

    Com a tolerancia de 1 quadro que estava aqui antes de tudo isso, **25 dos
    39 projetos (64%) eram recusados**: o usuario corrigia uma legenda e o
    apply respondia "OLD map Nf vs cut.mp4 Mf" sem aplicar nada. Foi 9 das 10
    falhas de apply registradas no historico dele.

    Continua pegando o caso que a guarda existe para pegar — mapa de OUTRO
    corte, que difere pelo tamanho de um range inteiro, tipicamente segundos.
    E ela e a rede SECUNDARIA: quem detecta corte refeito e o fingerprint das
    corrections (`_clear_dirty`), nao a contagem de quadros.

    Uma coisa que esta folga NAO faz e piorar o sincronismo. O remap e por
    span (`output_to_source` acha o span que contem o instante e mapeia
    dentro dele), entao a deriva ja existe no mapa desde o render original —
    recusar a correcao nunca consertou isso, so impediu o conserto do texto.
    A deriva em si e divida separada: [[extract_segment perde quadro de
    cabeca no `-ss`]].
    """
    return 2 + round(5.0 * math.sqrt(max(0, int(n_ranges))))


def prepare_edl_apply(edit_dir: Path) -> tuple[str | None, dict[str, Any] | None, list | None]:
    """Valida timeline + remap. Barato: sem FFmpeg, sem gravar captions.json."""
    from app.quick_corrections import _same_ranges

    old, new, fps, prior = caption_timeline_edls(edit_dir)
    old_map = build_timeline_map(old, fps=fps, prior_jcut=old.get("jcut_timeline"))
    new_map = build_timeline_map(new, fps=fps, prior_jcut=prior)
    err = validate_timeline_map(old_map) or validate_timeline_map(new_map)
    if err:
        return err, new_map, None
    cut_path = Path(edit_dir) / "cut.mp4"
    cut_frames = read_mp4_video_frames(cut_path) if cut_path.is_file() else None
    predicted = int(old_map.get("outputFrames") or 0)
    folga = tolerancia_de_quadros(len(old_map.get("spans") or []))
    if cut_frames and predicted and abs(predicted - cut_frames) > folga:
        return (
            f"OLD map {predicted}f vs cut.mp4 {cut_frames}f (folga {folga}f)",
            new_map,
            None,
        )
    words = _read_json(captions_path(edit_dir), [])
    if not isinstance(words, list):
        words = []
    words, _attach_err = attach_provenance_from_transcripts(words, old, edit_dir)
    amb = provenance_error(words, words, old_map)
    if amb:
        return amb, new_map, None
    current = [r for r in (new.get("ranges") or []) if isinstance(r, dict)]
    if not current or _same_ranges(old.get("ranges") or [], current):
        remapped = words
    else:
        remapped = remap_captions_between_timelines(words, old_map, new_map)
    err = validate_remapped_captions(words, remapped, new_map)
    return err, new_map, remapped


def _promote_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() == src.resolve():
        return
    # os.replace ja substitui atomicamente; o unlink previo que havia aqui
    # criava uma janela sem arquivo nenhum e, com o video aberto no player,
    # dava WinError 32 depois do render inteiro pronto.
    src.replace(dest)


def _probe_duration_real(path: Path) -> float:
    from app.media_probe import probe_video

    info = probe_video(path)
    if not info.get("ok"):
        raise ApplyError(info.get("error") or "não consegui ler a duração")
    return float(info.get("durationSec") or 0)


def _validate_final_real(
    path: Path,
    *,
    expected_duration: float | None = None,
    require_audio: bool = True,
) -> tuple[bool, dict[str, Any]]:
    from app.media_probe import probe_video

    if not path.is_file():
        return False, {"error": "arquivo não encontrado"}
    try:
        size = path.stat().st_size
    except OSError:
        return False, {"error": "arquivo ilegível"}
    if size < MIN_FINAL_BYTES:
        return False, {"error": "arquivo pequeno demais"}
    info = probe_video(path)
    if not info.get("ok"):
        return False, {"error": info.get("error") or "probe falhou"}
    dur = float(info.get("durationSec") or 0)
    if dur < 0.2:
        return False, {"error": "duração inválida"}
    if require_audio and not info.get("audio"):
        return False, {"error": "sem áudio"}
    if expected_duration and expected_duration > 0.4:
        if abs(dur - expected_duration) > max(1.5, expected_duration * 0.12):
            return False, {
                "error": "duração incompatível com o corte",
                "got": dur,
                "expected": expected_duration,
            }
    info["size"] = size
    return True, info


def _rebuild_cut_real(edit_dir: Path, dest: Path) -> Path:
    """Reconstrói o cut pelo EDL manual. Sem transcrição, sem plano de IA."""
    from pipeline.run_fast import _helper

    edl = edl_path(edit_dir)
    if not edl.exists():
        raise ApplyError("edl.json ausente")
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("MANUAL_EDL_REBUILD", flush=True)
    _helper("render.py", str(edl), "-o", str(dest), "--no-subtitles", "--voice-master")
    if not dest.is_file() or dest.stat().st_size < MIN_FINAL_BYTES:
        raise ApplyError("o novo corte não foi gerado")
    return dest


def _refazer_nota(edit_dir: Path, cut: Path, captions: list | None,
                  log: Any) -> None:
    """Recalcula `score.json` para o corte que acabou de ser promovido.

    A nota e do CORTE, e o apply refaz o corte. Medido nos projetos do
    usuario: 13 dos 17 que passaram por um apply ficaram com a nota velha,
    uma delas 90 horas velha — com dicas sobre pausas de um corte que nao
    existe mais.

    Sem `verificacao.json` novo nao ha como saber de pausa: entra
    `silence_flags=0` de proposito, e o arquivo velho e apagado logo
    abaixo. Afirmar pausa que ninguem mediu seria inventar.

    Nunca levanta: a nota e um extra, o video ja esta entregue.
    """
    edit = Path(edit_dir)
    try:
        import sys as _sys

        _h = str(Path(__file__).resolve().parent.parent / "helpers")
        if _h not in _sys.path:
            _sys.path.insert(0, _h)
        from video_score import score_structural  # type: ignore

        # A duracao sai DAQUI DE DENTRO: `_probe_duration_real` roda um
        # ffprobe e pode levantar, e nota nenhuma vale derrubar um apply
        # que ja entregou o video.
        duracao = float(_probe_duration_real(cut) or 0)
        edl = _read_json(edit / "edl.json", {}) or {}
        ranges = [r for r in (edl.get("ranges") or []) if isinstance(r, dict)]
        if not ranges or duracao <= 0:
            return
        falado = " ".join(
            str(w.get("text") or "").strip()
            for w in (captions or []) if isinstance(w, dict)
        ).strip()
        pedido = _read_json(edit / "job_intent.json", {}) or {}
        modo = str(pedido.get("editingIntent") or "dynamic")
        # O TIPO tambem isenta a regua de abertura curta (educativo,
        # informativo, institucional, review preservam por contrato) — o
        # apply grava a mesma `score.json` que o render, entao ele nao
        # pode julgar por outra regra.
        nota = score_structural(
            mode=modo,
            tipo=pedido.get("contentType"),
            duration=float(duracao),
            ranges=ranges,
            has_hook_beat=any(str(r.get("beat") or "").upper() == "HOOK"
                              for r in ranges),
            has_cta=any(str(r.get("beat") or "").upper() == "CTA"
                        for r in ranges),
            silence_flags=0,
            transcript_ok=True,
            spoken=falado,
        )
        _write_json(edit / "score.json", nota)
        # O diagnostico de audio descreve o corte ANTERIOR e nao da para
        # refaze-lo aqui sem reanalisar o audio. Mesmo criterio do run_fast:
        # diagnostico que nao vale nao sobrevive.
        try:
            (edit / "verificacao.json").unlink(missing_ok=True)
        except OSError:
            pass
        log(f"QUICK_APPLY_SCORE overall={nota.get('overall')}")
    except Exception as e:  # noqa: BLE001 — nota e extra, nunca o produto
        log(f"QUICK_APPLY_SCORE_FALHOU {type(e).__name__}: {e}")


def _touch_edit_data_duration(edit_dir: Path, duration: float, fps: float | None = None) -> None:
    """Atualiza só a duração. Não mexe em hook.lines (headline do operador)."""
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data["durationSec"] = round(float(duration), 4)
    if fps and fps > 1:
        data["fps"] = float(fps)
    _write_json(path, data)


def _avisar_redesenho(edit_dir: Path, feitos: int, total: int) -> None:
    """Quantos por cento do redesenho ja foram.

    O redesenho e 80,7% da espera de quem corrige uma legenda
    (mediana 52,4s, medido em 57 aplicacoes), e ate aqui a tela
    mostrava uma frase parada. Prever QUANTO FALTA ja foi tentado e
    reprovado (a faixa acertava 47%); contar o que JA FOI e verdade.
    """
    if total <= 0:
        return
    pct = min(99, max(1, round(100.0 * feitos / total)))
    try:
        write_apply_status(
            edit_dir, running=True, ok=None, stage="visual",
            message=f"Redesenhando o vídeo com as suas correções… {pct}%")
    except Exception:  # noqa: BLE001
        pass          # avisar nunca pode derrubar o render


def _render_visual_real(
    edit_dir: Path,
    *,
    cut: Path,
    captions: list | None,
    dest: Path,
) -> Path:
    """Fase visual do pipeline atual, sem Whisper e sem reescrever a headline."""
    from pipeline.run_fast import (
        _canary_validate_overlay,
        encode_final,
        scaffold_remotion,
    )

    edit = Path(edit_dir)
    public = edit / "remotion" / "public"
    public.mkdir(parents=True, exist_ok=True)
    edit_data = _read_json(edit_data_path(edit), {})
    if not isinstance(edit_data, dict):
        edit_data = {}

    duration = _probe_duration_real(cut)
    fps = float(edit_data.get("fps") or 30)
    _touch_edit_data_duration(edit, duration, fps)
    edit_data = _read_json(edit_data_path(edit), edit_data)
    # Midia posta na mao no editor (imagem, efeito, emoji). Sem isto ela so
    # entrava no render COMPLETO, e "Aplicar alteracoes" — que e o botao que
    # o usuario usa depois de mexer na linha do tempo — devolvia o video sem
    # ela, calado. A funcao e idempotente: aplicar de novo nao duplica.
    try:
        from pipeline.run_fast import midia_do_editor

        antes = json.dumps(edit_data, sort_keys=True)
        midia_do_editor(edit, public, edit_data)
        if json.dumps(edit_data, sort_keys=True) != antes:
            _write_json(edit_data_path(edit), edit_data)
    except Exception as e:  # noqa: BLE001 - midia nao pode derrubar o apply
        print(f"[warn] mídia do editor: {e}", flush=True)

    swaps: list[tuple[Path, Path]] = []
    caps_tmp: Path | None = None
    if captions is not None:
        caps_tmp = edit / TMP_CAPTIONS
        _write_json(caps_tmp, captions)
        swaps.append((public / "captions.json", caps_tmp))
    if cut.resolve() != (edit / "cut.mp4").resolve():
        swaps.append((public / "cut.mp4", cut))

    with _temp_install(swaps):
        if (public / "captions.json").exists() and str(
            (edit_data.get("captions") or {}).get("style") or edit_data.get("captions") or ""
        ).lower() == "stacked":
            try:
                from pipeline.run_fast import _helper

                _helper(
                    "caption_style.py",
                    "--captions", str(public / "captions.json"),
                    "-o", str(public / "caption-cues.json"),
                    "--lang", "pt",
                    "--max-sec", f"{duration:.6f}",
                    check=False,
                )
            except Exception:
                pass

        remotion = scaffold_remotion(edit, track="shortform")
        overlay_ok = False
        try:
            from app.overlay_path import overlay_on, try_overlay_final
            from app.render_path import classify_render_path
        except Exception:
            overlay_on = lambda: False  # noqa: E731
            try_overlay_final = None  # type: ignore
            classify_render_path = None  # type: ignore

        if overlay_on() and try_overlay_final and classify_render_path:
            edl = _read_json(edl_path(edit), {})
            cls = classify_render_path(edit_data, public=public, edl=edl, ffmpeg_zoom=True)
            if cls.get("path") != "FULL":
                try:
                    ov = try_overlay_final(
                        edit_dir=edit,
                        remotion=remotion,
                        cut=cut,
                        edit_data=edit_data,
                        duration=duration,
                        dest=dest,
                        progresso=lambda f, n: _avisar_redesenho(edit, f, n),
                    )
                    bad = _canary_validate_overlay(dest, edit_data, ov)
                    if bad:
                        raise RuntimeError(bad)
                    overlay_ok = True
                    _motor(edit, "overlay")
                except Exception as e:
                    print(f"QUICK_APPLY_OVERLAY_FALLBACK {e}", flush=True)
                    overlay_ok = False
                    _motor(edit, "remotion", str(e))
            else:
                _motor(edit, "remotion",
                       f"classificado FULL: {cls.get('fullReasons')}")

        if not overlay_ok:
            from app.timeline import timeline_from_edit_data
            from pipeline.run_fast import _remotion_cmd, _run_tool

            (remotion / "out").mkdir(exist_ok=True)
            rend = _run_tool(
                _remotion_cmd(remotion, "render", "Reels", "out/render.mp4"),
                cwd=remotion,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            if getattr(rend, "returncode", 1) != 0:
                raise ApplyError("não consegui aplicar o visual")
            tl = timeline_from_edit_data(edit_data)
            encode_final(
                edit,
                False,
                float(tl["durationSec"]),
                duration_in_frames=int(tl["durationInFrames"]),
                dest=dest,
            )

    if not dest.is_file():
        raise ApplyError("o vídeo final temporário não foi gerado")
    return dest


def _sync_pack_real(edit_dir: Path, final: Path) -> Path | None:
    from app.delivery_pack import ensure_delivery_pack, read_pack_dir

    if read_pack_dir(edit_dir) is None and not (Path(edit_dir).parent / "publicar").exists():
        packed = ensure_delivery_pack(edit_dir, final=final)
        return packed
    return ensure_delivery_pack(edit_dir, final=final)


@contextmanager
def _temp_install(swaps: list[tuple[Path, Path]]):
    """Copia arquivos temporários no lugar do live só durante o render; depois restaura."""
    backups: list[tuple[Path, Path]] = []
    try:
        for live, new in swaps:
            if not new.is_file():
                continue
            live.parent.mkdir(parents=True, exist_ok=True)
            bak = live.with_name(live.name + ".apply.bak")
            if live.exists():
                if bak.exists():
                    bak.unlink()
                shutil.copy2(live, bak)
                backups.append((live, bak))
                # O "Liberar espaço" liga public/cut.mp4 ao edit/cut.mp4 por
                # HARDLINK quando os bytes coincidem. copy2 por cima do live
                # TRUNCA o inode compartilhado: a fonte da verdade viraria o
                # temporário ainda nao validado — para sempre, calado, mesmo
                # com o restore abaixo (que troca a ENTRADA, nao o inode).
                live.unlink()
            shutil.copy2(new, live)
        yield
    finally:
        for live, bak in backups:
            try:
                if bak.exists():
                    if live.exists():
                        live.unlink()
                    bak.replace(live)
            except OSError as e:
                # Restore falhou = o temporario ficou instalado como live.
                # Sem esta linha ninguem sabia.
                print(f"APPLY_RESTORE_FALHOU {live.name}: {e}", flush=True)


def default_hooks(edit_dir: Path) -> ApplyHooks:
    return ApplyHooks(
        rebuild_cut=_rebuild_cut_real,
        render_visual=_render_visual_real,
        validate_final=_validate_final_real,
        promote_file=_promote_file,
        sync_pack=_sync_pack_real,
        probe_duration=_probe_duration_real,
        log=_log_do_apply(edit_dir),
        progress=_default_progress(edit_dir),
    )


def _cleanup_temps(edit_dir: Path) -> None:
    edit = Path(edit_dir)
    for name in (TMP_CUT, TMP_FINAL, TMP_CAPTIONS):
        p = edit / name
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
    public = edit / "remotion" / "public"
    for p in public.glob("*.apply.bak"):
        try:
            p.unlink()
        except OSError:
            pass
    for p in edit.glob("*.apply.bak"):
        try:
            p.unlink()
        except OSError:
            pass


def _stamp_captions_clock(edit_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Captions.json agora bate com o EDL aplicado. Fingerprint explícito, sem null."""
    ranges = read_edl_ranges(edit_dir)
    data["captionsTimedTo"] = _ranges_snapshot(ranges)
    edl = _read_json(edl_path(edit_dir), {}) or {}
    if not isinstance(edl, dict):
        edl = {}
    data["captionsTimedToJcut"] = _jcut_snapshot(edl.get("jcut_timeline"))
    fps = 0.0
    for src in (edl, _read_json(edit_data_path(edit_dir), {}) or {}):
        if not isinstance(src, dict):
            continue
        for key in ("fps", "targetFps"):
            try:
                val = float(src.get(key) or 0)
            except (TypeError, ValueError):
                val = 0.0
            if val > 0:
                fps = val
                break
        if fps > 0:
            break
    data["captionsTimedToFps"] = fps if fps > 0 else 30.0
    return data


# NAO PROMETER TEMPO AQUI. Tentei em 30/08 e o dado reprovou: ajustando
# uma reta nas 45 aplicacoes do motor proprio, `render ~ 10,6s fixos +
# 52,0 ms por quadro`, com erro de 32% na mediana e 75% no p90. Mesmo
# arredondando em faixas grossas ("menos de 1 minuto" / "cerca de N
# minutos"), a faixa acertava **21 de 45 vezes (47%)** — cara ou coroa.
# Dizer "cerca de 2 minutos" e levar 40s e pior que nao dizer nada.
#
# O caminho honesto ja esta ligado: o desenho conta o QUADRO em que esta,
# de `_render_visual_real` -> run_fast -> overlay_path -> motor proprio, e
# `_avisar_redesenho` transforma isso em porcentagem. Vale para os DOIS
# caminhos do motor — a passada unica (o padrao) e a de duas etapas; ligar
# so um deles deixava a barra parada em quase todo apply.


def record_apply_metric(edit_dir: Path, rec: dict[str, Any]) -> None:
    """Histórico local curto. Sem dashboard."""
    path = Path(edit_dir) / APPLY_HISTORY
    items: list[Any] = []
    if path.exists():
        loaded = _read_json(path, [])
        if isinstance(loaded, list):
            items = loaded
    row = {
        "at": rec.get("at") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": str(rec.get("type") or ""),
        "videoDuration": round(float(rec.get("videoDuration") or 0), 2),
        "applyDuration": round(float(rec.get("applyDuration") or 0), 1),
        "success": bool(rec.get("success")),
        **_colher(edit_dir),
    }
    if rec.get("dirty"):
        row["dirty"] = list(rec["dirty"])[:6]
    if rec.get("error"):
        row["error"] = str(rec["error"])[:160]
    items.append(row)
    _write_json(path, items[-APPLY_HISTORY_MAX:])


def _clear_dirty(edit_dir: Path) -> dict[str, Any]:
    data = load(edit_dir)
    data["dirty"] = empty_dirty()
    data["pending"] = {k: 0 for k in DIRTY_KEYS}
    data["finalStale"] = False
    # O snapshot de "Antes das correcoes rapidas" vale para o LOTE que acabou
    # de ser aplicado — daqui em diante ele e passado.
    #
    # `prepare_correction` so tira snapshot novo quando `revertVersionId` esta
    # vazio. Mantendo o id antigo, a correcao SEGUINTE reaproveitava o
    # snapshot de antes da anterior, e "Descartar" desfazia junto o trabalho
    # ja aplicado — que o usuario ja tinha visto no video. O laco que dispara
    # isso e o mais comum do editor: corrige, aplica, corrige de novo,
    # desiste.
    data["revertVersionId"] = None
    _stamp_captions_clock(edit_dir, data)
    data["appliedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return save(edit_dir, data)


def _snapshot_applied(edit_dir: Path, plan: dict[str, Any]) -> None:
    pending = plan.get("pending") or []
    label = "Correções aplicadas"
    if pending:
        label = "Correções aplicadas: " + ", ".join(str(x) for x in pending)
    try:
        from app.project_versions import snapshot

        snapshot(Path(edit_dir), origin="quick_apply", description=label[:120])
    except Exception:
        pass


def _current_final(edit_dir: Path) -> Path:
    from app.delivery_pack import resolve_final_mp4

    found = resolve_final_mp4(Path(edit_dir))
    return found if found is not None else Path(edit_dir) / "final.mp4"


def _conferir_pico(final: Path, log: Any) -> None:
    """O apply entrega dentro do limite de pico, como o render de um job novo.

    `garantir_true_peak` só era chamado pelo `run_fast`, então um vídeo que
    passa por "corrigir legenda" ou "mudar o corte" saía sem essa conferência.
    Na prática o apply refaz o final pelo MESMO `try_overlay_final`, herdando o
    mesmo alvo de loudnorm — medido nos 31 projetos do usuário com apply
    bem-sucedido, 30 estão dentro de -1,0 dBTP. O único fora é um arquivo em
    que nenhum caminho consegue baixar o pico (teve 3 applies, um por motor).

    Ou seja: é rede, não conserto de rotina. Custa um `ebur128` — 0,29s medido
    num final de 30 MB — e sai na hora quando já está dentro do limite. Quando
    encontra um final ANTIGO fora de especificação, conserta de vez.

    Chamar isto aqui só passou a ser seguro depois que `garantir_true_peak`
    parou de trocar o arquivo sem conferir se melhorou: em material teimoso o
    loudnorm PIORA o pico, e antes a piora ficava gravada.

    Nunca derruba o apply: o pico é acabamento, e recusar a correção de texto
    do usuário por causa dele seria pior que entregar 0,2 dB acima.
    """
    try:
        from app.overlay_compose import garantir_true_peak

        tp = garantir_true_peak(final).get("truePeakDb")
        if tp is not None:
            log(f"QUICK_APPLY_TRUE_PEAK {tp} dBTP")
            if float(tp) > -0.99:
                log(f"QUICK_APPLY_TRUE_PEAK_ALTO {tp} — entregue mesmo assim")
    except Exception as e:  # noqa: BLE001
        log(f"QUICK_APPLY_TRUE_PEAK_FALHOU {e}")


def _reembutir_capa(edit: Path, final: Path, log: Any) -> None:
    """Devolve a CAPA embutida que o apply perdia.

    `seal_delivery_cover` so roda no fim do pipeline completo; o apply refaz o
    final.mp4 do zero e o arquivo promovido saia SEM o JPEG anexado
    (`attached_pic`) — que e o que o Instagram usa como capa ao postar. Medido
    nos entregues do usuario: dos que passaram por apply, quase todos estavam
    sem a capa; dos que vieram so do pipeline, 13 de 15 tinham.

    NAO chama `seal_delivery_cover` quando ja existe `cover.jpg`: aquele
    regenera a capa a partir do quadro 0, e `cover.jpg` pode ser uma capa que
    o USUARIO escolheu pelo botao Capa do editor — regenerar atropelava a
    escolha dele. Com o arquivo existente, so o remux barato de anexar.
    """
    try:
        from app.overlay_compose import _ffmpeg, probe_json

        streams = probe_json(final).get("streams") or []
        if any((st.get("disposition") or {}).get("attached_pic") for st in streams):
            return                        # ja tem capa — nada a fazer
        cover = edit / "cover.jpg"
        if not cover.is_file():
            # nunca houve capa: gera do zero pelo caminho do pipeline
            from pipeline.run_fast import seal_delivery_cover

            seal_delivery_cover(edit, final)
            log("QUICK_APPLY_COVER_SEAL")
            return
        tagged = edit / "_final_tagged.mp4"
        r = subprocess.run(
            [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(final), "-i", str(cover),
             "-map", "0", "-map", "1",
             "-c", "copy", "-c:v:1", "mjpeg",
             "-disposition:v:1", "attached_pic",
             "-movflags", "+faststart", str(tagged)],
            capture_output=True, text=True, timeout=120,
            **({"creationflags": subprocess.CREATE_NO_WINDOW}
               if hasattr(subprocess, "CREATE_NO_WINDOW") else {}),
        )
        if r.returncode == 0 and tagged.is_file() and tagged.stat().st_size > 1000:
            os.replace(tagged, final)
            log("QUICK_APPLY_COVER_OK")
        else:
            tagged.unlink(missing_ok=True)
            log(f"QUICK_APPLY_COVER_WARN {(r.stderr or '')[-160:]}")
    except Exception as e:  # noqa: BLE001 — capa nunca derruba o apply
        log(f"QUICK_APPLY_COVER_WARN {e}")


def _so_legenda_mudou(plan: dict[str, Any]) -> bool:
    """True quando so ha mudanca LOCALIZAVEL: texto da legenda e/ou headline.

    Estilo e corte mexem em quadros espalhados (ou em todos) — ai nao ha fatia
    para emendar. A headline entrou depois: ela vive nos primeiros segundos do
    video (janela [0, hook.endSec]), entao trocar o texto dela e uma fatia
    unica no comeco — e era o apply mais comum a pagar o render completo, ja
    que o editor oferece 3 opcoes de titulo justamente para trocar.
    """
    if str(plan.get("mode") or "") != "REUSE_CUT":
        return False
    if plan.get("rebuildCut") or plan.get("remapCaptions"):
        return False
    sujo = plan.get("dirty") or {}
    if any(sujo.get(k) for k in ("edl", "style")):
        return False
    return bool(sujo.get("captions") or sujo.get("headline"))


def _tentar_emenda(edit: Path, plan: dict[str, Any], *, cut: Path, dest: Path,
                   log: Any) -> bool:
    """Refaz so a fatia da legenda mexida. False = siga pelo caminho normal.

    Nunca e a unica saida: qualquer recusa, erro ou divergencia na conferencia
    cai no render completo, que e o que sempre foi feito.
    """
    if (os.environ.get("ATIVAVID_EMENDA") or "").strip() == "0":
        return False
    if not _so_legenda_mudou(plan):
        return False
    try:
        from app.caption_fixes import load_stored_fixes
        from app.emenda_legenda import emendar_legenda
        from app.timeline import timeline_from_edit_data

        public = edit / "remotion" / "public"
        edit_data = _read_json(public / "edit-data.json", {})
        if not isinstance(edit_data, dict) or not edit_data:
            return False
        sujo = plan.get("dirty") or {}
        cues = _read_json(public / "caption-cues.json", None)
        fixes = load_stored_fixes(edit) if sujo.get("captions") else []
        if sujo.get("captions") and (not cues or not fixes):
            return False
        janelas_extra: list[tuple[int, int]] = []
        if sujo.get("headline"):
            hook = edit_data.get("hook") or {}
            if not hook.get("enabled"):
                return False
            # Headline em duas fases (pergunta -> resposta): a RESPOSTA
            # aparece mais tarde, fora da janela do hook — emendar so o
            # comeco deixaria a resposta velha no video. Caminho cheio.
            if hook.get("answerLines"):
                return False
            fps_ed = float(edit_data.get("fps") or 30)
            fim_hl = float(hook.get("endSec") or 4.0)
            tl_tmp = timeline_from_edit_data(edit_data)
            janelas_extra.append(
                (0, min(int(tl_tmp["durationInFrames"]),
                        int(round(fim_hl * fps_ed)) + 8)))
        if not fixes and not janelas_extra:
            return False
        tl = timeline_from_edit_data(edit_data)
        final_atual = _current_final(edit)
        pq: list = []
        saida = emendar_legenda(
            edit,
            motivo=pq,
            public=public,
            edit_data=edit_data,
            cut=cut,
            final=final_atual,
            cues=cues,
            fixes=fixes,
            frames=int(tl["durationInFrames"]),
            fps=float(edit_data.get("fps") or 30),
            width=int(edit_data.get("width") or 1080),
            height=int(edit_data.get("height") or 1920),
            dest=dest,
            janelas_extra=janelas_extra,
        )
    except Exception as e:  # noqa: BLE001
        log(f"QUICK_APPLY_EMENDA_ERRO {e}")
        return False
    if saida is None:
        # O motivo vai para o apply_history via `_colher` -- e o que vai
        # decidir, com dados de producao, se vale generalizar a emenda para
        # multi-fatia (a envolvente unica estoura o teto em 89% dos casos
        # reais; a estimativa multi-fatia passa em 67%).
        if pq:
            log(f"QUICK_APPLY_EMENDA_PULADA {pq[0][:120]}")
            with _METRICAS_LOCK:
                _ULTIMO_MOTOR.setdefault(_chave(edit), {})["emendaSkip"] = pq[0][:160]
        return False
    log("QUICK_APPLY_EMENDA_OK")
    _ULTIMO_MOTOR.setdefault(_chave(edit), {})["engine"] = "emenda"
    return True


def execute_apply_plan(
    edit_dir: Path,
    plan: dict[str, Any] | None = None,
    *,
    hooks: ApplyHooks | None = None,
) -> dict[str, Any]:
    """Executa exatamente o plano. Nunca transcreve, nunca chama IA."""
    edit = Path(edit_dir)
    plan = plan or plan_apply_changes(load(edit))
    hooks = hooks or default_hooks(edit)
    log = hooks.log

    if not plan.get("renderVisual") and plan.get("mode") == "NOOP":
        return {
            "ok": True,
            "noop": True,
            "plan": plan,
            "execute": True,
            "message": "Nada para aplicar",
        }

    if plan.get("runTranscription") or plan.get("runAI"):
        raise ApplyError("plano inválido: Apply não pode transcrever nem chamar IA")

    write_apply_status(
        edit,
        running=True,
        ok=None,
        message="Aplicando alterações...",
        stage="start",
        error=None,
    )
    log("QUICK_APPLY_START")
    log(
        "QUICK_APPLY_PLAN "
        + str(plan.get("mode") or "")
        + (" REMAP_CAPTIONS" if plan.get("remapCaptions") else "")
        + " "
        + str(plan.get("renderMode") or "")
    )

    cut_tmp = edit / TMP_CUT
    final_tmp = edit / TMP_FINAL
    caps_tmp = edit / TMP_CAPTIONS
    live_cut = edit / "cut.mp4"
    live_final = _current_final(edit)
    caps_new: list | None = None
    prepared_caps: list | None = None
    new_map: dict[str, Any] | None = None
    t_all = time.time()
    with _METRICAS_LOCK:
        _FASES.pop(_chave(edit), None)

    try:
        if plan.get("rebuildCut") or plan.get("remapCaptions"):
            err, new_map, prepared_caps = prepare_edl_apply(edit)
            if err:
                log(f"QUICK_APPLY_INVARIANT {err}")
                # O motivo conhecido vem ANTES da frase generica: e aqui
                # que a mensagem e escolhida, e o `user_message` explicito
                # vencia o mapa la embaixo.
                user = (PROVENANCE_FAIL_MSG if err == OVERLAP_FAIL
                        else (motivo_do_apply(err) or PREPARE_FAIL_MSG))
                raise PrepareError(err, user_message=user)

        if plan.get("rebuildCut"):
            hooks.progress("cutting", "Atualizando cortes...")
            log("MANUAL_EDL_REBUILD")
            t0 = time.time()
            hooks.rebuild_cut(edit, cut_tmp)
            log(f"QUICK_APPLY_REBUILD_SEC {_fase(edit, 'cut', t0):.3f}")
            work_cut = cut_tmp
            predicted = int((new_map or {}).get("outputFrames") or 0)
            actual = read_mp4_video_frames(cut_tmp)
            # o mapa expoe `spans` (um por range), nao `ranges`
            folga = tolerancia_de_quadros(len((new_map or {}).get("spans") or []))
            log(f"QUICK_APPLY_CUT_FRAMES predicted={predicted} actual={actual} "
                f"folga={folga}")
            if predicted and actual is not None and abs(int(actual) - predicted) > folga:
                raise ApplyError(
                    f"cut temporário tem {actual} frames, o mapa previa "
                    f"{predicted} (folga {folga})"
                )
        else:
            hooks.progress("prepare", "Preparando alterações...")
            log("QUICK_APPLY_REUSE_CUT")
            if not live_cut.is_file():
                raise ApplyError("este vídeo ainda não tem corte para reaproveitar")
            work_cut = live_cut

        if plan.get("remapCaptions"):
            t0 = time.time()
            caps_new = prepared_caps
            if caps_new is None:
                caps_new = pending_caption_remap(edit)
            if caps_new is None:
                words = _read_json(captions_path(edit), [])
                caps_new = words if isinstance(words, list) else []
            _write_json(caps_tmp, caps_new)
            log("CAPTIONS_REMAP_APPLIED")
            log(f"QUICK_APPLY_REMAP_SEC {_fase(edit, 'remap', t0):.3f}")

        # "Aplicando edição..." nao dizia o que estava acontecendo no
        # minuto mais longo da espera (80,7% do tempo, mediana 52,4s).
        hooks.progress("visual",
                       "Redesenhando o vídeo com as suas correções…")
        log("QUICK_APPLY_RENDER_VISUAL")
        t0 = time.time()
        if not _tentar_emenda(edit, plan, cut=work_cut, dest=final_tmp, log=log):
            hooks.render_visual(edit, cut=work_cut, captions=caps_new, dest=final_tmp)
        log(f"QUICK_APPLY_RENDER_SEC {_fase(edit, 'render', t0):.3f}")

        _conferir_pico(final_tmp, log)

        hooks.progress("export", "Finalizando vídeo...")
        expected = None
        if plan.get("rebuildCut"):
            expected = expected_output_duration(edit)
        t0 = time.time()
        ok, info = hooks.validate_final(final_tmp, expected_duration=expected, require_audio=True)
        if not ok:
            raise ApplyError(str((info or {}).get("error") or "validação falhou"))
        log("QUICK_APPLY_VALIDATE_OK")
        log(f"QUICK_APPLY_VALIDATE_SEC {_fase(edit, 'validate', t0):.3f}")

        t0 = time.time()
        if caps_new is not None:
            _write_json(captions_path(edit), caps_new)
        if plan.get("rebuildCut") and cut_tmp.is_file():
            hooks.promote_file(cut_tmp, live_cut)
            # O corte mudou: a copia leve que o editor usa esta velha. Sem
            # isto ela ficava velha PARA SEMPRE — 46 dos 186 projetos do
            # usuario estavam assim, um deles por 3,7 dias.
            try:
                import sys as _sys

                _h = str(Path(__file__).resolve().parent.parent / "helpers")
                if _h not in _sys.path:
                    _sys.path.insert(0, _h)
                from make_proxy import refazer_em_fundo  # type: ignore

                refazer_em_fundo(live_cut, edit)
            except Exception as e:  # noqa: BLE001 — nunca derruba o apply
                log(f"PROXY_REFAZER_FALHOU {type(e).__name__}: {e}")
            public_cut = edit / "remotion" / "public" / "cut.mp4"
            if public_cut.parent.is_dir():
                try:
                    shutil.copy2(live_cut, public_cut)
                except OSError:
                    pass
        hooks.promote_file(final_tmp, live_final)
        if live_final.name != "final.mp4":
            hard = edit / "final.mp4"
            if hard.resolve() != live_final.resolve():
                try:
                    shutil.copy2(live_final, hard)
                except OSError:
                    pass
        log("QUICK_APPLY_PROMOTE_FINAL")
        # A nota e do CORTE, e o corte acabou de mudar. Sem isto ela ficava
        # descrevendo o corte anterior — 13 dos 17 projetos do usuario que
        # passaram por um apply estavam assim, um deles ha 90 horas.
        if plan.get("rebuildCut"):
            _refazer_nota(edit, live_cut, caps_new, log)
        # Titulo trocado = ARQUIVO renomeado. O conteudo ja saia certo, mas o
        # nome do mp4, o state.finalVideo e a pasta publicar/ ficavam com o
        # titulo VELHO — visto no fluxo real: trocar para "FLUXO REAL DO
        # APPLY" e a entrega continuar "O menino, sabe onde tem o mercado
        # aqui". Reusa o mecanismo do pipeline (promote_final_headline), que
        # renomeia, apaga o leftover antigo e nunca derruba o apply — em erro
        # devolve o arquivo como esta. Antes da capa e do sync_pack, para a
        # pasta publicar/ mudar de nome junto (o pack MOVE quando o nome
        # muda).
        if (plan.get("dirty") or {}).get("headline"):
            try:
                import sys as _sys

                _repo = str(Path(__file__).resolve().parent.parent)
                if _repo not in _sys.path:
                    _sys.path.insert(0, _repo)
                from pipeline.run_fast import promote_final_headline

                ed_atual = _read_json(
                    edit / "remotion" / "public" / "edit-data.json", {})
                novo = promote_final_headline(edit, live_final, ed_atual, None)
                if novo != live_final and novo.is_file():
                    live_final = novo
                    _write_json(edit / "state.json", {
                        **_read_json(edit / "state.json", {}),
                        "finalVideo": novo.name,
                    })
                    # `final.mp4` e a copia de conveniencia que o resto do app
                    # espera existir. Quando o live_final ERA o final.mp4, o
                    # rename o move — repoe a copia com o conteudo atual.
                    hard = edit / "final.mp4"
                    if novo.resolve() != hard.resolve():
                        try:
                            shutil.copy2(novo, hard)
                        except OSError:
                            pass
                    log(f"QUICK_APPLY_RENAME {novo.name}")
            except Exception as e:  # noqa: BLE001
                log(f"QUICK_APPLY_RENAME_ERRO {e}")
        # a capa volta ANTES do sync_pack, para o entregue em publicar/ ja
        # sair com ela
        _reembutir_capa(edit, live_final, log)
        if live_final.name != "final.mp4":
            hard = edit / "final.mp4"
            if hard.resolve() != live_final.resolve() and hard.is_file():
                try:
                    shutil.copy2(live_final, hard)
                except OSError:
                    pass

        packed = None
        try:
            packed = hooks.sync_pack(edit, live_final)
        except Exception as e:
            log(f"QUICK_APPLY_PACK_WARN {e}")

        corr = _clear_dirty(edit)
        _snapshot_applied(edit, plan)
        _cleanup_temps(edit)
        write_apply_status(
            edit,
            running=False,
            ok=True,
            message="Vídeo atualizado",
            stage="done",
            error=None,
            at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        log(f"QUICK_APPLY_PROMOTE_SEC {_fase(edit, 'promote', t0):.3f}")
        log("QUICK_APPLY_SUCCESS")
        log(f"QUICK_APPLY_TOTAL_SEC {time.time() - t_all:.3f}")
        dur = float((info or {}).get("durationSec") or 0)
        if dur <= 0 and expected:
            dur = float(expected)
        record_apply_metric(edit, {
            "type": plan.get("mode") or "",
            "videoDuration": dur,
            "applyDuration": time.time() - t_all,
            "success": True,
            # O QUE estava sujo: sem isto um REUSE_CUT de 45s por troca de
            # estilo (redesenho legitimo) e indistinguivel de uma emenda
            # perdida na auditoria do apply_history (visto em 25/08: 6
            # applies "overlay" sem como saber por que a emenda nao rodou).
            "dirty": sorted(k for k, v in (plan.get("dirty") or {}).items() if v),
        })
        return {
            "ok": True,
            "plan": plan,
            "execute": True,
            "final": str(live_final),
            "packed": str(packed) if packed else None,
            "corrections": corr,
            "message": "Vídeo atualizado",
            "validate": info,
        }
    except Exception as e:
        _cleanup_temps(edit)
        # O motivo VEM PRIMEIRO quando se conhece: a frase generica so
        # informa que nada mudou, e o usuario fica sem saber o que fazer.
        msg = (getattr(e, "user_message", None)
               or motivo_do_apply(str(e))
               or (PREPARE_FAIL_MSG if isinstance(e, PrepareError)
                   else FAIL_MSG))
        write_apply_status(
            edit,
            running=False,
            ok=False,
            message=msg,
            stage="error",
            error=str(e)[:300],
            at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        log(f"QUICK_APPLY_FAIL {e}")
        try:
            record_apply_metric(edit, {
                "type": (plan or {}).get("mode") or "",
                "videoDuration": 0,
                "applyDuration": time.time() - t_all,
                "success": False,
                "error": str(e)[:160],
                "dirty": sorted(k for k, v in ((plan or {}).get("dirty") or {}).items() if v),
            })
        except Exception:
            pass
        return {
            "ok": False,
            "plan": plan,
            "execute": True,
            "prepareFailed": isinstance(e, PrepareError),
            "error": str(e)[:400],
            "message": msg,
            "corrections": load(edit),
        }


def start_apply(
    edit_dir: Path,
    *,
    hooks: ApplyHooks | None = None,
    fallback_full: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Dispara o Apply em thread. A UI consulta apply_status.json.

    fallback_full: reenfileira o projeto no pipeline completo quando o
    atalho rápido não consegue garantir legendas alinhadas (PrepareError,
    ex.: mapa da timeline divergiu do cut.mp4). Sem isto o projeto ficava
    travado — toda tentativa de Apply falhava para sempre. O rerun completo
    mantém o corte manual (load_manual_edl_ranges)."""
    edit = Path(edit_dir)
    if is_apply_running(edit):
        return {
            "ok": False,
            "busy": True,
            "error": "Já estou aplicando as alterações deste vídeo.",
            "corrections": load(edit),
        }
    plan = plan_apply_changes(load(edit))
    if plan.get("mode") == "NOOP":
        return {
            "ok": True,
            "noop": True,
            "plan": plan,
            "execute": True,
            "message": "Nada para aplicar",
            "corrections": load(edit),
        }
    try:
        from app.apply_tasks import STATUS_QUEUED, STAGE_PREPARING, register_task

        register_task(edit, status=STATUS_QUEUED, stage=STAGE_PREPARING)
    except Exception:
        pass
    write_apply_status(
        edit,
        running=False,
        ok=None,
        message="Na fila...",
        stage="queued",
        pid=os.getpid(),
    )

    def _run() -> None:
        from app.job_slots import acquire as acquire_slot
        from app.job_slots import release as release_slot

        if not acquire_slot(timeout=3600):
            write_apply_status(
                edit,
                running=False,
                ok=False,
                message=motivo_do_apply("fila cheia") or FAIL_MSG,
                error="fila cheia",
                stage="error",
            )
            return
        write_apply_status(
            edit,
            running=True,
            ok=None,
            message="Aplicando alterações...",
            stage="start",
            pid=os.getpid(),
        )
        try:
            res = execute_apply_plan(edit, plan, hooks=hooks)
            if (not res.get("ok")) and res.get("prepareFailed") and fallback_full is not None:
                delegated = False
                try:
                    delegated = bool(fallback_full())
                except Exception:
                    delegated = False
                if delegated:
                    write_apply_status(
                        edit,
                        running=False,
                        ok=None,
                        message="Reprocessando o vídeo inteiro (seus cortes são mantidos)...",
                        stage="queued",
                        error=None,
                    )
                    # Por último: o job do pipeline assume o card da Fila; a
                    # tarefa de Apply sai de cena (write_apply_status acima
                    # ressincroniza a task, então o clear vem depois dela).
                    try:
                        from app.apply_tasks import clear_task

                        clear_task(edit)
                    except Exception:
                        pass
        except Exception as e:
            write_apply_status(
                edit,
                running=False,
                ok=False,
                message=FAIL_MSG,
                error=str(e)[:300],
                stage="error",
            )
        finally:
            release_slot()

    import threading

    threading.Thread(target=_run, daemon=True, name="quick-apply").start()
    apply_task = None
    try:
        from app.apply_tasks import public_view, read_task

        apply_task = public_view(read_task(edit), edit)
    except Exception:
        apply_task = None
    return {
        "ok": True,
        "started": True,
        "plan": plan,
        "execute": True,
        "message": "Aplicando alterações...",
        "corrections": load(edit),
        "applyStatus": read_apply_status(edit),
        "applyTask": apply_task,
    }
