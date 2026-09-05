"""Mapa canônico fonte → cut.mp4. Uma matemática só: a do J-cut em render.py.

Captions e a duração do cut usam este mapa. Não casa range só por segundo:
IMG 0–2.7 e CTA 0–2.7 são takes diferentes.

A duração do ARQUIVO não é a soma crua dos floats do plano. Cada take é
extraído com ffmpeg `-t DUR -r FPS` (CFR) e o concat soma frames inteiros
(_mkseg.py / write_segments_json).
"""
from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

# Mesmos defaults de helpers/render.py (plan_jcut / jcut_settings).
JCUT_LEAD_FRAMES = 5
JCUT_TAIL_TRIM_FRAMES = 2
MIN_DUR = 1e-4


def _range_dicts(edl: Any) -> list[dict]:
    raw = edl.get("ranges") if isinstance(edl, dict) else edl
    out: list[dict] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        if end > start:
            item = dict(r)
            item["start"] = start
            item["end"] = end
            item["source"] = str(r.get("source") or "SRC")
            out.append(item)
    return out


def _fps_of(edl: Any, fallback: float = 30.0) -> float:
    if not isinstance(edl, dict):
        return fallback
    for key in ("fps", "targetFps"):
        try:
            val = float(edl.get(key) or 0)
        except (TypeError, ValueError):
            val = 0.0
        if val > 0:
            return val
    return fallback


def jcut_enabled(edl: Any) -> bool:
    """J-cut só quando o cut real usa (timeline gravada, flag, ou duração planejada).

    Fixture de teste sem esses campos continua na soma dos ranges — o rebuild
    de um projeto renderizado sempre tem total_duration_s ou jcut_timeline.
    """
    if not isinstance(edl, dict):
        return False
    ranges = _range_dicts(edl)
    if len(ranges) < 2:
        return False
    cfg = edl.get("jcut", None)
    if cfg is False or cfg in ("off", "none"):
        return False
    if cfg is True or isinstance(cfg, dict):
        return True
    if isinstance(edl.get("jcut_timeline"), list) and edl.get("jcut_timeline"):
        return True
    try:
        if float(edl.get("total_duration_s") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def encoded_video_frames(duration_s: float, fps: float) -> int:
    """Quantos frames o extract emite: `ffmpeg -t DUR -r FPS` em CFR.

    O frame n começa em n/fps e entra no arquivo se n/fps < DUR.
    DUR é o mesmo `{duration:.6f}` de helpers/render.py extract_segment.
    Não é um pad mágico no total — é a quantização por take, depois concat.
    """
    t = round(float(duration_s), 6)
    fps_f = float(fps)
    if t <= 0 or fps_f <= 0:
        return 0
    return max(1, math.floor(t * fps_f - 1e-9) + 1)


def read_mp4_video_frames(path: Path) -> int | None:
    """Conta samples da track de vídeo no container. Sem FFmpeg."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    tracks: list[dict[str, Any]] = []

    def walk(start: int, end: int, ctx: dict[str, Any] | None) -> None:
        i = start
        while i + 8 <= end:
            size = struct.unpack(">I", data[i : i + 4])[0]
            typ = data[i + 4 : i + 8]
            hdr = 8
            if size == 1 and i + 16 <= end:
                size = struct.unpack(">Q", data[i + 8 : i + 16])[0]
                hdr = 16
            elif size == 0:
                size = end - i
            if size < hdr or i + size > end:
                break
            payload = i + hdr
            box_end = i + size
            if typ == b"trak":
                inner: dict[str, Any] = {"hdlr": None, "stsz": None}
                walk(payload, box_end, inner)
                tracks.append(inner)
            elif typ == b"hdlr" and ctx is not None and box_end >= payload + 12:
                ctx["hdlr"] = data[payload + 8 : payload + 12]
            elif typ == b"stsz" and ctx is not None and box_end >= payload + 12:
                _ver, count = struct.unpack(">II", data[payload + 4 : payload + 12])
                ctx["stsz"] = int(count)
            elif typ in (b"moov", b"mdia", b"minf", b"stbl"):
                walk(payload, box_end, ctx)
            i = box_end

    walk(0, len(data), None)
    for tr in tracks:
        if tr.get("hdlr") == b"vide" and int(tr.get("stsz") or 0) > 0:
            return int(tr["stsz"])
    return None


def layout_jcut_spans(
    ranges: list[dict],
    *,
    fps: float,
    lead_frames: int,
    tail_frames: list[int],
) -> list[dict]:
    """Offsets de vídeo/áudio do J-cut. Sem FFmpeg.

    Cópia da conta em helpers/render.py plan_jcut:
      a_in, a_out = start, end - tail
      v_in = start + lead (exceto o primeiro)
      v_off += v_dur
      a_off += a_dur - lead
    """
    fps_f = float(fps) if float(fps) > 0 else 30.0
    lead = max(0, int(lead_frames)) / fps_f
    a_off = 0.0
    v_off = 0.0
    out: list[dict] = []
    for i, r in enumerate(ranges):
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        tf = int(tail_frames[i]) if i < len(tail_frames) else 0
        tail = max(0, tf) / fps_f
        a_in, a_out = start, max(start, end - tail)
        v_in = start + (lead if i > 0 else 0.0)
        v_out = a_out
        if v_out < v_in:
            v_out = v_in
        a_dur = max(0.0, a_out - a_in)
        v_dur = max(0.0, v_out - v_in)
        src = str(r.get("source") or "SRC")
        out.append({
            "source": src,
            "beat": r.get("beat"),
            "sourceStart": a_in,
            "sourceEnd": a_out,
            "edlStart": start,
            "edlEnd": end,
            "outputStart": a_off,
            "outputEnd": a_off + a_dur,
            "videoStart": v_off,
            "videoEnd": v_off + v_dur,
            "audioStart": a_off,
            "audioEnd": a_off + a_dur,
            "tailFrames": tf,
            "leadSec": lead if i > 0 else 0.0,
            "a_in": a_in,
            "a_out": a_out,
            "a_off": a_off,
            "v_in": v_in,
            "v_out": v_out,
            "v_off": v_off,
        })
        v_off += v_dur
        # `max(0, ...)`: o passo nunca pode ser negativo. O J-cut adianta o
        # audio do proximo take em `lead` (5 quadros); num take mais CURTO que
        # isso, `a_dur - lead` fica negativo e o relogio de saida ANDA PARA
        # TRAS — o take seguinte comeca antes do anterior.
        #
        # E alcancavel pela UI: `split_at_playhead` aceita segmento de 0,2s
        # (MIN_SEG), e lead+tail consomem 0,2333s a 30fps. Reproduzido com
        # ranges [0-5, 5-5.21, CTA 0-3]: o terceiro span comecava 23ms antes
        # do segundo.
        #
        # Nao e so o mapa: `helpers/render.py` usa esta MESMA funcao e o
        # `a_off` vira o `adelay` do audio daquele take — ou seja, no video
        # entregue a fala de um take entrava por cima da do anterior.
        #
        # Com o clamp, o take curto adianta o quanto ele tem (todo o proprio
        # comprimento) e para ai.
        a_off += max(0.0, a_dur - lead)
    return out


VELOCIDADES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)


def velocidade_do_range(r: dict) -> float:
    """Velocidade pedida para UM trecho (5.0.56). 1 = normal.

    Fora da lista o valor e ignorado: o `atempo` do ffmpeg so aceita
    0,5-100 (abaixo disso e preciso encadear), e uma velocidade qualquer
    vinda da tela derrubaria o corte inteiro.
    """
    try:
        v = float(r.get("speed") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return v if v in VELOCIDADES else 1.0


CONGELAR_MAX = 5.0


def congelar_do_range(r: dict) -> float:
    """Segundos de quadro congelado no FIM deste take (5.0.58).

    O "congelar" do CapCut: o ultimo quadro fica parado por um instante —
    usado para carimbar um numero, uma seta, uma reacao. Teto de 5 s: acima
    disso e um cartao, nao um efeito de corte.
    """
    try:
        v = float(r.get("freeze") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return round(min(max(v, 0.0), CONGELAR_MAX), 2)


def tem_velocidade(ranges) -> bool:
    return any(velocidade_do_range(r) != 1.0 or congelar_do_range(r) > 0
               for r in (ranges or []) if isinstance(r, dict))


def _naive_spans(ranges: list[dict]) -> list[dict]:
    acc = 0.0
    out: list[dict] = []
    for r in ranges:
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        vel = velocidade_do_range(r)
        congelar = congelar_do_range(r)
        # camera lenta estica, acelerado encurta: a duracao na SAIDA e a da
        # fonte dividida pela velocidade (0,5x dobra; 2x corta pela metade).
        # O quadro congelado entra DEPOIS, como cauda parada.
        dur = max(0.0, end - start) / vel + congelar
        src = str(r.get("source") or "SRC")
        out.append({
            "source": src,
            "speed": vel,
            "freeze": congelar,
            "beat": r.get("beat"),
            "sourceStart": start,
            "sourceEnd": end,
            "edlStart": start,
            "edlEnd": end,
            "outputStart": acc,
            "outputEnd": acc + dur,
            "videoStart": acc,
            "videoEnd": acc + dur,
            "audioStart": acc,
            "audioEnd": acc + dur,
            "tailFrames": 0,
            "leadSec": 0.0,
            "a_in": start,
            "a_out": end,
            "a_off": acc,
            "v_in": start,
            "v_out": end,
            "v_off": acc,
        })
        acc += dur
    return out


def spans_from_jcut_timeline(ranges: list[dict], jcut: list) -> list[dict] | None:
    """Usa o jcut_timeline gravado pelo render — o cut real.

    Recusa timeline velha: CTA 0–3.4 gravado não descreve CTA 0–2.7 atual.
    """
    if not isinstance(jcut, list) or len(jcut) != len(ranges):
        return None
    out: list[dict] = []
    for r, j in zip(ranges, jcut):
        if not isinstance(j, dict):
            return None
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        src = str(r.get("source") or "SRC")
        jsrc = str(j.get("source") or src)
        if jsrc != src:
            return None
        a_dur = float(j.get("audio_duration") or 0)
        if a_dur <= 0:
            a_dur = max(0.0, end - start)
        if a_dur > (end - start) + 0.05:
            return None
        a_off = float(j.get("audio_start_in_output") or 0)
        v_off = float(j.get("video_start_in_output") or 0)
        v_dur = float(j.get("video_duration") or max(0.0, end - start))
        tf = int(j.get("tail_trim_frames") or 0)
        a_in = start
        a_out = start + a_dur
        out.append({
            "source": src,
            "beat": r.get("beat") or j.get("beat"),
            "sourceStart": a_in,
            "sourceEnd": a_out,
            "edlStart": start,
            "edlEnd": end,
            "outputStart": a_off,
            "outputEnd": a_off + a_dur,
            "videoStart": v_off,
            "videoEnd": v_off + v_dur,
            "audioStart": a_off,
            "audioEnd": a_off + a_dur,
            "tailFrames": tf,
            "leadSec": max(0.0, v_off - a_off) if v_off > a_off else 0.0,
            "a_in": a_in,
            "a_out": a_out,
            "a_off": a_off,
            "v_in": start + max(0.0, v_off - a_off),
            "v_out": a_out,
            "v_off": v_off,
        })
    return out


def infer_tail_frames(
    ranges: list[dict],
    *,
    prior_jcut: list | None = None,
    default_tail: int = JCUT_TAIL_TRIM_FRAMES,
) -> list[int]:
    """Último take: 0. Os do meio: tail do jcut anterior se a source bater, senão o default."""
    n = len(ranges)
    tails = [0 if i == n - 1 else int(default_tail) for i in range(n)]
    if not isinstance(prior_jcut, list) or not prior_jcut:
        return tails
    used: set[int] = set()
    for i, r in enumerate(ranges):
        if i == n - 1:
            tails[i] = 0
            continue
        src = str(r.get("source") or "")
        for j, jt in enumerate(prior_jcut):
            if j in used or not isinstance(jt, dict):
                continue
            if str(jt.get("source") or "") != src:
                continue
            used.add(j)
            # `is not None`, nao OR: zero e um tail GRAVADO, nao "vazio".
            # `plan_jcut` devolve 0 sempre que o take termina em fala (o
            # silencio final nao cobre nem um quadro). Medido nos projetos do
            # usuario: 269 das 1047 entradas gravadas sao 0 (26%), e 55 dos
            # 111 projetos tem um 0 num take que NAO e o ultimo.
            #
            # Com o OR, esse 0 virava 2 e o take perdia 66,7ms de audio. Como
            # `a_off += a_dur - lead` acumula, TODOS os spans seguintes ficavam
            # cedo demais no mapa novo, e as legendas — carimbadas por
            # `outputStart` — apareciam antes da palavra. A funcao irma
            # `_lead_frames_of`, logo abaixo, ja fazia `is not None`.
            v = jt.get("tail_trim_frames")
            tails[i] = max(0, int(v)) if v is not None else int(default_tail)
            break
    return tails


def _lead_frames_of(edl: Any) -> int:
    cfg = edl.get("jcut") if isinstance(edl, dict) else None
    if isinstance(cfg, dict) and cfg.get("lead_frames") is not None:
        return max(0, int(cfg.get("lead_frames") or 0))
    return JCUT_LEAD_FRAMES


def build_timeline_map(
    edl: Any,
    *,
    fps: float | None = None,
    prior_jcut: list | None = None,
) -> dict[str, Any]:
    """Mapa fonte→saída. Prefere jcut_timeline gravado; senão prevê a conta do rebuild."""
    ranges = _range_dicts(edl)
    fps_f = float(fps) if fps and fps > 0 else _fps_of(edl)
    edl_jcut = None
    if isinstance(edl, dict) and isinstance(edl.get("jcut_timeline"), list):
        edl_jcut = edl.get("jcut_timeline")
    prior = prior_jcut if isinstance(prior_jcut, list) else None
    use_jcut = jcut_enabled(edl)
    if use_jcut:
        # Só a timeline DESTE EDL. prior_jcut é o cut anterior — serve para
        # inferir tails, não para posicionar ranges novos.
        # Com velocidade em algum trecho, o `jcut_timeline` do render ANTERIOR
        # descreve outra geometria — cair no caminho ingenuo e o certo.
        spans = (None if tem_velocidade(ranges)
                 else spans_from_jcut_timeline(ranges, edl_jcut or []))
        if spans is None:
            tails = infer_tail_frames(ranges, prior_jcut=prior or edl_jcut)
            spans = layout_jcut_spans(
                ranges,
                fps=fps_f,
                lead_frames=_lead_frames_of(edl),
                tail_frames=tails,
            )
    else:
        spans = _naive_spans(ranges)
    video_dur = spans[-1]["videoEnd"] if spans else 0.0
    audio_dur = max((float(s["outputEnd"]) for s in spans), default=0.0)
    frames = 0
    for span in spans:
        v_dur = float(span["videoEnd"]) - float(span["videoStart"])
        n = encoded_video_frames(v_dur, fps_f)
        span["videoFrames"] = n
        frames += n
    encoded_dur = (frames / fps_f) if fps_f > 0 else video_dur
    return {
        "spans": spans,
        "fps": fps_f,
        "jcut": use_jcut,
        "videoDuration": video_dur,
        "audioDuration": audio_dur,
        "plannedDuration": video_dur,
        "outputFrames": frames,
        "outputDuration": encoded_dur,
    }


def map_output_duration(timeline: dict[str, Any] | None) -> float:
    if not timeline:
        return 0.0
    return float(timeline.get("outputDuration") or 0.0)


def validate_timeline_map(timeline: dict[str, Any] | None) -> str | None:
    if not timeline or not isinstance(timeline.get("spans"), list):
        return "timeline map ausente"
    prev_v = -1.0
    prev_o = -1.0
    for span in timeline["spans"]:
        if not isinstance(span, dict):
            return "span inválido"
        if not str(span.get("source") or "").strip():
            return "source ausente"
        if float(span.get("sourceEnd") or 0) + 1e-9 < float(span.get("sourceStart") or 0):
            return "segmento com duração negativa"
        vs = float(span.get("videoStart") or 0)
        ve = float(span.get("videoEnd") or 0)
        if ve + 1e-9 < vs:
            return "segmento com duração negativa"
        if vs + 1e-6 < prev_v:
            return "timeline não é monotônica"
        prev_v = vs
        # O eixo de SAIDA tambem, nao so o de video. E nele que as legendas
        # vivem (`outputStart`), e ele podia andar para tras sem que esta
        # funcao percebesse: com o take mais curto que o `lead` do J-cut,
        # `videoStart` ficava parado (v_dur=0) e a checagem passava enquanto
        # dois spans de fontes diferentes cobriam o mesmo instante.
        os_ = float(span.get("outputStart") or 0)
        oe = float(span.get("outputEnd") or 0)
        if oe + 1e-9 < os_:
            return "segmento com duração negativa na saída"
        if os_ + 1e-6 < prev_o:
            return "relógio de saída não é monotônico"
        prev_o = os_
    return None
