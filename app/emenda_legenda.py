# -*- coding: utf-8 -*-
"""Corrigir uma palavra sem redesenhar o vídeo inteiro.

O CUSTO QUE ISTO ATACA. No histórico do usuário, um apply de legenda
(`REUSE_CUT`) tem mediana de **384 s** e pior caso de **1806 s** — meia hora
para trocar uma palavra. A razão é que o caminho normal redesenha todos os
quadros e reencoda o arquivo todo, mesmo quando quase nada mudou.

QUANTO MUDA DE VERDADE. Medido nos 114 projetos reais, corrigindo a palavra
do meio: o vídeo tem 1446 quadros de mediana, o incremental de hoje
redesenharia 774 (ele vai do ponto da mudança até o FIM) e o que realmente
precisa mudar são **64 quadros — 4,5% do vídeo**. Mediana de 10,4x só no
desenho, e é o encode que sobra depois.

COMO. Três pedaços: a cabeça e a cauda do final saem por `-c copy` (nada é
reencodado), e só a fatia do meio é recomposta a partir do `cut.mp4` limpo com
o overlay novo. A emenda cai em KEYFRAME dos dois lados, senão o `copy` não
fecha. O áudio não muda numa correção de texto, então ele é copiado inteiro do
final antigo — sem loudnorm, sem reencode.

A MESMA TÉCNICA JÁ ESTÁ NO REPO: `_seal_cover_head_splice` (pipeline/run_fast)
carimba a capa reencodando só o primeiro GOP. A diferença aqui é que a fatia
fica no MEIO, então são três pedaços em vez de dois.

QUANDO NÃO VALE. Se a fatia cobrir quase tudo, emendar é mais caro que
refazer (três processos de ffmpeg + validação). Por isso `FRACAO_MAXIMA`.

Qualquer divergência na conferência final — contagem de quadros, duração ou um
decode que reclame — devolve `None` e quem chamou segue pelo caminho normal.
Isto é um ATALHO, nunca a única saída.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# Acima disto a emenda não paga: o trabalho de recortar, recompor, concatenar
# e conferir passa a competir com só refazer. Medido em 114 projetos, uma
# correção de palavra fica em 4,5% — bem longe da barra.
FRACAO_MAXIMA = 0.45
# Folga em quadros dos dois lados da cue mexida: a palavra trocada muda a
# largura da linha e pode reagrupar a cue em curso, e a saída tem fade.
FOLGA_ANTES = 30
FOLGA_DEPOIS = 12


def _ffmpeg() -> str:
    from app.overlay_compose import _ffmpeg as _f

    return _f()


def _ffprobe() -> str:
    from app.overlay_compose import _ffprobe as _f

    return _f()


def _run(argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **NOWIN)


def keyframes(path: Path) -> list[float]:
    """Instantes (s) dos keyframes do fluxo de vídeo, em ordem.

    Lê PACOTES, não quadros: `-show_packets` não decodifica nada, então isto
    custa dezenas de milissegundos mesmo num arquivo de 90 s. Com
    `-show_frames` o mesmo trabalho decodificaria o vídeo inteiro — o que
    sozinho já custaria mais do que a emenda economiza.
    """
    r = _run([
        _ffprobe(), "-v", "error", "-select_streams", "v:0",
        "-show_packets", "-show_entries", "packet=pts_time,flags",
        "-of", "json", str(path),
    ], timeout=120)
    if r.returncode != 0:
        return []
    try:
        pacotes = (json.loads(r.stdout or "{}").get("packets") or [])
    except json.JSONDecodeError:
        return []
    saida = []
    for p in pacotes:
        if "K" not in str(p.get("flags") or ""):
            continue
        t = p.get("pts_time")
        if t in (None, "", "N/A"):
            continue
        try:
            saida.append(float(t))
        except (TypeError, ValueError):
            continue
    return sorted(saida)


def janela_das_correcoes(
    cues: Any, fixes: list, *, fps: float, frames: int,
) -> tuple[int, int] | None:
    """Quadros [ini, fim) afetados por estas correcoes de legenda.

    A janela sai das PROPRIAS correcoes, localizando o texto de destino nas
    cues ja corrigidas. Depender de um retrato das cues antigas nao serve: o
    caminho de uma passada (o padrao hoje) nao guarda overlay nenhum, entao
    esse retrato simplesmente nao existe na maioria dos jobs.

    `None` quando nao da para localizar com seguranca — dai o apply segue pelo
    caminho normal, que e sempre o certo, so mais caro.
    """
    from app.caption_fixes import _split_tokens, resolve_replacement_index

    lista = cues if isinstance(cues, list) else (cues or {}).get("cues")
    if not isinstance(lista, list) or not lista or not fixes:
        return None

    # cada palavra de cue, com a cue de onde veio
    palavras: list[dict] = []
    dono: list[int] = []
    for i, c in enumerate(lista):
        if not isinstance(c, dict):
            return None
        for ln in c.get("lines") or []:
            for w in ln or []:
                if not isinstance(w, dict):
                    return None
                palavras.append(w)
                dono.append(i)
    if not palavras:
        return None

    tocadas: set[int] = set()
    for fix in fixes:
        if not isinstance(fix, dict):
            continue
        alvo = str(fix.get("to") or "").strip()
        if not alvo:
            # apagar: o texto sumiu das cues, entao nao da para localizar por
            # ele. A janela ficaria adivinhada — melhor recusar.
            return None
        toks = _split_tokens(alvo)
        if not toks:
            return None
        status, hits = resolve_replacement_index(palavras, toks, fix)
        if status != "ok" or not hits:
            return None
        for h in hits:
            for k in range(len(toks)):
                if h + k < len(dono):
                    tocadas.add(dono[h + k])
    if not tocadas:
        return None

    ms_ini = min(float(lista[i].get("startMs") or 0) for i in tocadas)
    ms_fim = max(float(lista[i].get("endMs") or 0) for i in tocadas)
    if ms_fim <= ms_ini:
        return None
    ini = max(0, int(ms_ini / 1000.0 * fps) - FOLGA_ANTES)
    fim = min(frames, int(ms_fim / 1000.0 * fps) + FOLGA_DEPOIS)
    return (ini, fim) if fim > ini else None


def _limites_em_keyframe(
    kfs: list[float], *, ini_f: int, fim_f: int, fps: float, dur: float,
) -> tuple[float, float] | None:
    """Expande [ini_f, fim_f) até os keyframes que os contêm.

    Devolve (t_ini, t_fim) em segundos. `t_ini` é 0.0 quando a fatia começa
    antes do primeiro keyframe útil; `t_fim` é a duração quando ela vai até o
    fim. Sem keyframe do lado direito não há emenda possível — a cauda
    copiada começaria no meio de um GOP e o `copy` sairia quebrado.
    """
    if not kfs:
        return None
    t_ini_alvo = ini_f / fps
    t_fim_alvo = fim_f / fps
    antes = [t for t in kfs if t <= t_ini_alvo + 1e-6]
    t_ini = max(antes) if antes else 0.0
    depois = [t for t in kfs if t >= t_fim_alvo - 1e-6]
    if depois:
        t_fim = min(depois)
    elif t_fim_alvo >= dur - 1e-3:
        t_fim = dur          # a fatia vai até o fim: não há cauda para copiar
    else:
        return None
    if t_fim <= t_ini:
        return None
    return t_ini, t_fim


def _intervalos_desenhados(
    cues: Any, edit_data: dict[str, Any], dur: float,
) -> list[tuple[float, float]]:
    """Elementos que NAO podem ficar partidos pela costura.

    So a manchete e o cartao final. As legendas ficaram de fora de proposito, e
    a razao e dos dados: medido no projeto do usuario, as cues sao CONTIGUAS —
    folga zero em 48 de 48 emendas. Nao existe vao entre legendas onde a
    costura pudesse cair, entao exigir isso e impossivel por construcao: a
    primeira tentativa alargava de uma cue para a seguinte em cadeia e a fatia
    ia a 71% do video, matando o atalho em todo caso real.

    E o risco de uma cue partida e pequeno: a metade copiada e a metade
    redesenhada so diferem se o MOTOR mudou entre o render e a correcao — no
    caso normal, corrigir um video feito pela mesma versao, as duas metades sao
    desenhadas identicas e nao ha costura nenhuma. Ja a manchete e o cartao sao
    grandes, ficam parados na tela varios segundos e sao poucos: alargar por
    eles custa quase nada e um deles pela metade seria obvio.
    """
    saida: list[tuple[float, float]] = []
    hook = edit_data.get("hook") or {}
    if hook.get("enabled"):
        saida.append((0.0, float(hook.get("endSec") or 4.0)))
    ec = edit_data.get("endCard") or {}
    if ec.get("enabled"):
        saida.append((max(0.0, dur - float(ec.get("lastSec") or 2.5)), dur))
    return saida


def _alargar_ate_nao_partir(
    intervalos: list[tuple[float, float]], *, t_ini: float, t_fim: float,
    dur: float,
) -> tuple[float, float] | None:
    """Cresce a fatia ate nenhum elemento ficar METADE emendado.

    O trecho emendado e desenhado pelo motor de HOJE; o resto e copiado de um
    render que pode ser de outra versao. Enquanto a costura cai ENTRE elementos
    isso nao aparece — mas uma legenda que comeca antes da costura e termina
    depois seria desenhada de dois jeitos, com um salto no meio dela.

    Alargar, e nao recusar: a margem de 30 quadros antes da cue corrigida cai
    quase sempre dentro da cue anterior, entao recusar ai matava o atalho em
    praticamente todo caso real (medido: 0 de 2 rodadas).
    """
    for _ in range(8):
        partidos = [(a, b) for a, b in intervalos
                    if (a < t_ini < b) or (a < t_fim < b)]
        if not partidos:
            return t_ini, t_fim
        t_ini = min([t_ini] + [a for a, _ in partidos])
        t_fim = max([t_fim] + [b for _, b in partidos])
        t_ini = max(0.0, t_ini)
        t_fim = min(dur, t_fim)
    return None


def _desenhar_fatia(
    public: Path, edit_data: dict[str, Any], *,
    ini_f: int, n: int, frames: int, fps: float, width: int, height: int,
    cut: Path, t_ini: float, dest: Path,
) -> bool:
    """Recompoe [ini_f, ini_f+n) a partir do cut limpo + overlay novo.

    O `Renderizador` é construído com o total REAL de quadros da composição —
    nunca com `n`. O cartão final é ancorado no FIM, e um total artificial o
    faria aparecer no meio da fatia. (Foi exatamente esse engano que deu
    "razão 2,0" no comparador contra o Remotion.)
    """
    import numpy as np

    from app.render_engine import encoder_args
    from app.render_proprio import Renderizador

    r = Renderizador(public, edit_data, frames=frames, fps=fps,
                     width=width, height=height)
    enc, extra = encoder_args()
    argv = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t_ini:.6f}", "-i", str(cut),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}",
        "-r", f"{fps:g}", "-i", "-",
        "-filter_complex",
        # A MESMA cadeia do caminho de uma passada (render_proprio.py), na
        # mesma ordem. Faltavam `format=yuv420p` e sobretudo
        # `scale=in_range=full:out_range=limited`: sem a conversao de FAIXA o
        # trecho emendado sai com nivel diferente do resto do arquivo, que e
        # copiado — uma costura visivel. Medido: os quadros da fatia diferiam
        # do render completo em ~10 de 255, enquanto dois renders completos sao
        # bit a bit identicos.
        f"[0:v]trim=end_frame={n},fps={fps:g},setpts=PTS-STARTPTS[cutv];"
        f"[1:v]setpts=PTS-STARTPTS[ovl];"
        f"[cutv][ovl]overlay=eof_action=pass:format=auto,"
        f"format=yuv420p,"
        f"scale=in_range=full:out_range=limited,"
        f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]",
        "-map", "[vid]", "-an",
        "-c:v", enc, *extra,
        "-frames:v", str(n), str(dest),
    ]
    ff = subprocess.Popen(argv, stdin=subprocess.PIPE, **NOWIN)
    buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    ass_ant, bytes_ant = None, None
    try:
        for f in range(ini_f, ini_f + n):
            ass = r._assinatura(f)
            if ass == ass_ant and bytes_ant is not None:
                ff.stdin.write(bytes_ant)
                continue
            ass_ant = ass
            if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
                buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
            sujo[:] = [0, 0, 0, 0]
            primeira = True
            for leg in r.camadas:
                if leg.inicio_f <= f <= leg.fim_f:
                    if leg.dim:
                        r._aplicar_dim(buf, sujo, leg.dim, f - leg.inicio_f,
                                       leg.dim_fade)
                        primeira = False
                    r.desenhar(leg, f - leg.inicio_f, buf, sujo, mesclar=not primeira)
                    primeira = False
            for at in r.flashes:
                a = r._flash_quadro(at, f)
                if a is not None:
                    r._aplicar_flash(buf, sujo, a)
            bytes_ant = buf.tobytes()
            ff.stdin.write(bytes_ant)
    except OSError:
        pass                      # cano fechou: o returncode conta o que houve
    finally:
        try:
            ff.stdin.close()
        except OSError:
            pass
        ff.wait()
    return ff.returncode == 0 and dest.is_file() and dest.stat().st_size > 10_000


def emendar_legenda(
    edit_dir: Path, *, public: Path, edit_data: dict[str, Any],
    cut: Path, final: Path, cues: Any, fixes: list,
    frames: int, fps: float, width: int = 1080, height: int = 1920,
    dest: Path | None = None,
) -> Path | None:
    """Refaz só a fatia mexida e emenda no final. `None` = siga o caminho normal."""
    from app.overlay_compose import count_frames, video_info

    t0 = time.perf_counter()
    if not (final.is_file() and cut.is_file()):
        return None
    janela = janela_das_correcoes(cues, fixes, fps=fps, frames=frames)
    if janela is None:
        print("EMENDA_PULADA nao localizei a fatia com seguranca", flush=True)
        return None
    ini_f, fim_f = janela
    fracao = (fim_f - ini_f) / max(1, frames)
    if fracao > FRACAO_MAXIMA:
        print(f"EMENDA_PULADA fatia={fracao * 100:.0f}% > {FRACAO_MAXIMA * 100:.0f}%",
              flush=True)
        return None

    dur = float((video_info(final) or {}).get("duration") or 0.0)
    if dur <= 0:
        return None
    kfs = keyframes(final)
    elementos = _intervalos_desenhados(cues, edit_data, dur)
    lim = None
    for _ in range(4):
        lim = _limites_em_keyframe(kfs, ini_f=ini_f, fim_f=fim_f, fps=fps, dur=dur)
        if lim is None:
            break
        # alarga ate nenhum elemento ficar partido, e volta a alinhar em
        # keyframe (o alargamento pode ter tirado a fatia do keyframe)
        alargado = _alargar_ate_nao_partir(
            elementos, t_ini=lim[0], t_fim=lim[1], dur=dur)
        if alargado is None:
            lim = None
            break
        if abs(alargado[0] - lim[0]) < 1e-6 and abs(alargado[1] - lim[1]) < 1e-6:
            break
        ini_f = max(0, int(alargado[0] * fps))
        fim_f = min(frames, int(round(alargado[1] * fps)))
    if lim is None:
        print("EMENDA_PULADA nao consegui fechar a costura entre elementos",
              flush=True)
        return None
    t_ini, t_fim = lim
    fracao = (t_fim - t_ini) / max(1e-6, dur)
    if fracao > FRACAO_MAXIMA:
        print(f"EMENDA_PULADA fatia={fracao * 100:.0f}% depois de alargar "
              f"> {FRACAO_MAXIMA * 100:.0f}%", flush=True)
        return None
    kf_ini_f = int(round(t_ini * fps))
    n = int(round((t_fim - t_ini) * fps))
    if n <= 0 or kf_ini_f + n > frames:
        return None

    trab = edit_dir / "_emenda"
    trab.mkdir(parents=True, exist_ok=True)
    meio = trab / "meio.mp4"
    cabeca = trab / "cabeca.mp4"
    cauda = trab / "cauda.mp4"
    lista = trab / "concat.txt"
    juntos = trab / "juntos.mp4"
    saida = Path(dest) if dest is not None else trab / "final.mp4"
    try:
        if not _desenhar_fatia(public, edit_data, ini_f=kf_ini_f, n=n,
                               frames=frames, fps=fps, width=width,
                               height=height, cut=cut, t_ini=t_ini, dest=meio):
            print("EMENDA_FALHOU desenho da fatia", flush=True)
            return None

        pedacos: list[Path] = []
        if t_ini > 1e-6:
            # `-frames:v`, nao `-t`. Com `-c copy` o corte por TEMPO acontece no
            # pacote e passa do ponto: medido neste projeto, `-t 19,4667` deu
            # 586 quadros onde a fatia comeca no 584 — dois quadros duplicados
            # na emenda, e a conferencia (com razao) reprovava o arquivo.
            r = _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                      "-i", str(final), "-frames:v", str(kf_ini_f),
                      "-map", "0:v:0", "-c:v", "copy", "-an", str(cabeca)])
            if r.returncode != 0 or not cabeca.is_file():
                print("EMENDA_FALHOU cabeca", flush=True)
                return None
            pedacos.append(cabeca)
        pedacos.append(meio)
        if t_fim < dur - 1e-3:
            r = _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                      "-ss", f"{t_fim:.6f}", "-i", str(final),
                      "-map", "0:v:0", "-c:v", "copy", "-an", str(cauda)])
            if r.returncode != 0 or not cauda.is_file():
                print("EMENDA_FALHOU cauda", flush=True)
                return None
            pedacos.append(cauda)

        lista.write_text(
            "".join(f"file '{p.resolve().as_posix()}'\n" for p in pedacos),
            encoding="utf-8")
        r = _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                  "-f", "concat", "-safe", "0", "-i", str(lista),
                  "-c", "copy", str(juntos)])
        if r.returncode != 0 or not juntos.is_file():
            print(f"EMENDA_FALHOU concat {(r.stderr or '')[-200:]}", flush=True)
            return None

        # O áudio vem INTEIRO do final antigo: uma correção de texto não mexe
        # em som nenhum, então copiar evita reencode e um novo loudnorm (que
        # mudaria o pico e poderia derrubar a validação do canary).
        r = _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                  "-i", str(juntos), "-i", str(final),
                  "-map", "0:v:0", "-map", "1:a:0?", "-c", "copy",
                  "-movflags", "+faststart", str(saida)])
        if r.returncode != 0 or not saida.is_file():
            print(f"EMENDA_FALHOU mux {(r.stderr or '')[-200:]}", flush=True)
            return None

        got = int(count_frames(saida) or 0)
        if got != frames:
            partes = " ".join(
                f"{x.stem}={count_frames(x)}" for x in pedacos if x.is_file())
            print(f"EMENDA_REPROVADA quadros {got}!={frames} "
                  f"[{partes}] t_ini={t_ini:.4f} t_fim={t_fim:.4f} n={n}",
                  flush=True)
            return None
        got_sec = float((video_info(saida) or {}).get("duration") or 0.0)
        if abs(got_sec - dur) > 0.08:
            print(f"EMENDA_REPROVADA duracao {got_sec}!={dur}", flush=True)
            return None
        # decode completo: concat de pedaços com parâmetros diferentes pode
        # produzir arquivo que só reclama na hora de tocar
        r = _run([_ffmpeg(), "-v", "error", "-i", str(saida), "-f", "null", "-"])
        if r.returncode != 0 or (r.stderr or "").strip():
            print(f"EMENDA_REPROVADA decode {(r.stderr or '')[-200:]}", flush=True)
            return None

        print(f"EMENDA_OK {n}/{frames} quadros ({n / frames * 100:.1f}%) "
              f"em {time.perf_counter() - t0:.1f}s", flush=True)
        return saida
    finally:
        for p in (cabeca, cauda, juntos, lista):
            p.unlink(missing_ok=True)
