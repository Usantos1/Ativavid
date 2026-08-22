# -*- coding: utf-8 -*-
"""Confere tudo ANTES da rodada longa.

O benchmark pode levar horas de GPU e cota de API. Descobrir no vídeo 6 que
faltava uma chave é caro e evitável — este script pergunta tudo antes, em
segundos, e diz exatamente o que fazer para cada item que falta.

    python tools/bench_transcricao/preflight.py --corpus corpus.json

Sai com 0 se der para rodar os quatro cenários principais, 1 se der para rodar
uma parte, 2 se nem o cenário B (local, sem chave) sai do lugar.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

OK, AVISO, FALTA = "ok  ", "aviso", "FALTA"


class Relato:
    def __init__(self) -> None:
        self.linhas: list[tuple[str, str, str, str]] = []

    def add(self, nivel: str, item: str, detalhe: str, conserto: str = "") -> None:
        self.linhas.append((nivel, item, detalhe, conserto))

    def faltando(self) -> list[str]:
        return [i for n, i, _, _ in self.linhas if n == FALTA]

    def imprimir(self) -> None:
        larg = max(len(i) for _, i, _, _ in self.linhas)
        for nivel, item, detalhe, conserto in self.linhas:
            print(f"[{nivel}] {item.ljust(larg)}  {detalhe}")
            if conserto:
                print(f"{' ' * (larg + 8)}→ {conserto}")


def _ffmpeg(r: Relato) -> None:
    for exe in ("ffmpeg", "ffprobe"):
        caminho = shutil.which(exe)
        if caminho:
            r.add(OK, exe, caminho)
        else:
            r.add(FALTA, exe, "não encontrado no PATH",
                  "instale o FFmpeg — sem ele nenhum cenário roda, nem o local")


def _gpu(r: Relato) -> None:
    try:
        from app.transcricao.plataforma import detectar, resumo_tecnico

        m = detectar()
        if m.backend == "cuda":
            r.add(OK, "GPU", f"{m.gpu_nome} · {m.vram_mb} MB · backend=cuda")
        else:
            r.add(AVISO, "GPU", f"backend={m.backend} ({m.motivo or 'sem CUDA'})",
                  "o cenário B vai rodar em CPU e o modelo cai de medium para "
                  "small — os números de tempo não valerão para produção")
        r.add(OK, "plataforma", resumo_tecnico().strip().splitlines()[0])
    except Exception as e:  # noqa: BLE001
        r.add(AVISO, "GPU", f"não deu para detectar: {type(e).__name__}: {e}")


def _faster_whisper(r: Relato) -> None:
    try:
        import faster_whisper

        r.add(OK, "faster-whisper", getattr(faster_whisper, "__version__", "?"))
    except ImportError:
        r.add(FALTA, "faster-whisper", "não instalado",
              "uv sync --extra transcricao-cuda")


def _modelo(r: Relato, modelo: str) -> None:
    """O modelo já está no disco? Baixar 1,4 GB no meio da rodada atrapalha
    a medição de tempo do primeiro vídeo."""
    try:
        from app.transcricao import modelos as cat
        from app.transcricao.plataforma import detectar, pasta_de_modelos

        m = cat.escolher_modelo(detectar().vram_mb, modelo,
                                backend=detectar().backend)
        pasta = pasta_de_modelos()
        achado = list(pasta.glob(f"*{m.chave}*")) if pasta.is_dir() else []
        if achado:
            r.add(OK, f"modelo {m.chave}", str(achado[0]))
        else:
            r.add(AVISO, f"modelo {m.chave}", f"ainda não está em {pasta}",
                  "a primeira transcrição baixa sozinha (~"
                  f"{m.mb} MB); rode um vídeo curto antes para não contaminar "
                  "a medição de tempo")
    except Exception as e:  # noqa: BLE001
        r.add(AVISO, "modelo", f"não deu para conferir: {type(e).__name__}: {e}")


def _chaves(r: Relato) -> None:
    if os.environ.get("ELEVENLABS_API_KEY"):
        r.add(OK, "ELEVENLABS_API_KEY", "definida (cenário A)")
    else:
        r.add(FALTA, "ELEVENLABS_API_KEY", "ausente — cenário A não roda",
              "set ELEVENLABS_API_KEY=...")

    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        r.add(OK, "GEMINI_API_KEY", "definida (cenários C e D)")
    else:
        r.add(FALTA, "GEMINI_API_KEY", "ausente — cenários C e D não rodam",
              "set GEMINI_API_KEY=...  (o gateway de sessão web do projeto "
              "não envia áudio, por isso C e D precisam da API)")

    try:
        import google.genai  # noqa: F401

        r.add(OK, "google-genai", "instalado")
    except ImportError:
        r.add(FALTA, "google-genai", "não instalado — cenários C e D não rodam",
              "uv pip install google-genai")


def _sessao_ia(r: Relato) -> None:
    """Cenário E e o planejador de cortes usam a sessão web que já existe."""
    try:
        from app.llm_gateway import status

        st = status()
        if st.get("ok"):
            r.add(OK, "sessão IA", f"{st.get('backend')} — cenário E e --cortes")
        else:
            r.add(AVISO, "sessão IA", st.get("message") or "sem sessão",
                  "capture na extensão; sem isso o cenário E e o --cortes "
                  "ficam de fora, mas A–D seguem")
    except Exception as e:  # noqa: BLE001
        r.add(AVISO, "sessão IA", f"{type(e).__name__}: {e}")


def _corpus(r: Relato, caminho: Path) -> None:
    if not caminho.is_file():
        r.add(FALTA, "corpus", f"{caminho} não existe",
              "copie corpus.exemplo.json para corpus.json e preencha")
        return
    try:
        d = json.loads(caminho.read_text(encoding="utf-8"))
        videos = d.get("videos") or []
    except ValueError as e:
        r.add(FALTA, "corpus", f"JSON inválido: {e}")
        return

    faltando = [v["id"] for v in videos
                if not v.get("video") or not Path(v["video"]).expanduser().is_file()]
    if faltando:
        r.add(FALTA, "corpus", f"{len(faltando)} vídeo(s) sem arquivo: "
              f"{', '.join(faltando[:5])}",
              "corrija os caminhos em corpus.json")
    if len(videos) < 8:
        r.add(AVISO, "corpus", f"{len(videos)} vídeo(s) — o pedido é ≥ 8",
              "menos que isso e uma diferença de 1 vídeo vira 12% da média")
    elif not faltando:
        r.add(OK, "corpus", f"{len(videos)} vídeos, todos no disco")

    tags = {t for v in videos for t in v.get("tags", [])}
    esperadas = {"uma_pessoa", "duas_ou_mais", "girias", "nomes_proprios",
                 "marcas", "numeros", "ruido", "musica_fundo", "fala_rapida",
                 "coloquial_br"}
    if tags:
        sem = esperadas - tags
        if sem:
            r.add(AVISO, "cobertura", f"sem material marcado: {', '.join(sorted(sem))}",
                  "o relatório não vai poder dizer onde cada motor falha "
                  "nessas situações")
        else:
            r.add(OK, "cobertura", f"{len(tags)} situações cobertas")

    duracao = 0.0
    if shutil.which("ffprobe"):
        for v in videos[:50]:
            p = Path(v.get("video") or "").expanduser()
            if not p.is_file():
                continue
            try:
                out = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nokey=1:noprint_wrappers=1", str(p)],
                    capture_output=True, text=True, timeout=30).stdout.strip()
                duracao += float(out or 0)
            except (ValueError, subprocess.SubprocessError):
                pass
    if duracao:
        r.add(OK, "duração total", f"{duracao / 60:.1f} min de áudio",
              f"estimativa grosseira: cenário B ~{duracao / 60 / 2.7:.0f} min "
              f"em GPU; A, C e D somam upload + espera de API")


def _custos(r: Relato) -> None:
    p = Path(__file__).resolve().parent / "custos.json"
    if not p.is_file():
        r.add(AVISO, "custos.json", "não existe — linha de custo sairá vazia")
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    vazios = [k for k, v in d.items()
              if isinstance(v, dict)
              and any(x is None for x in v.values() if not isinstance(x, str))]
    if vazios:
        r.add(AVISO, "custos.json", f"sem preço: {', '.join(vazios)}",
              "preencha antes de publicar custo; sem isso o relatório mostra "
              "'sem dado', que é o certo mas não responde a pergunta")
    else:
        r.add(OK, "custos.json", "preenchido")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--modelo", default="medium")
    a = ap.parse_args()

    r = Relato()
    _ffmpeg(r)
    _faster_whisper(r)
    _gpu(r)
    _modelo(r, a.modelo)
    _chaves(r)
    _sessao_ia(r)
    _corpus(r, Path(a.corpus))
    _custos(r)
    r.imprimir()

    falta = set(r.faltando())
    print()
    bloqueia_tudo = {"ffmpeg", "ffprobe", "faster-whisper", "corpus"} & falta
    if bloqueia_tudo:
        print(f"PARADO: {', '.join(sorted(bloqueia_tudo))} — nem o cenário "
              f"local roda assim.")
        return 2
    if falta:
        print(f"PARCIAL: dá para rodar, mas {', '.join(sorted(falta))} deixam "
              f"cenários de fora. O relatório marca as células como 'sem dado'.")
        return 1
    print("TUDO PRONTO. python tools/bench_transcricao/rodar.py "
          f"--corpus {a.corpus} --saida bench/ --cortes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
