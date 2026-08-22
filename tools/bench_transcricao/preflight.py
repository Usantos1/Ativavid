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

    # Gemini: sessão web por cookies, sem chave e sem custo de API. É o que o
    # projeto usa, e o benchmark não introduz caminho pago.
    try:
        from app.llm_gateway import status

        st = status()
        if st.get("hasGemini"):
            r.add(OK, "sessão Gemini",
                  f"capturada · {st.get('backend')} (cenário E, sem custo)")
        elif st.get("ok"):
            r.add(AVISO, "sessão Gemini",
                  f"sem Gemini; há {st.get('backend')} — o cenário E rodaria "
                  f"por outro modelo",
                  "capture a sessão do Gemini na extensão para o cenário E "
                  "medir o que o produto usa de verdade")
        else:
            r.add(FALTA, "sessão Gemini",
                  st.get("message") or "não capturada — cenário E não roda",
                  "abra gemini.google.com logado e capture na extensão")
    except Exception as e:  # noqa: BLE001
        r.add(FALTA, "sessão Gemini", f"{type(e).__name__}: {e}",
              "o cenário E depende de app/llm_gateway.py")

    r.add(AVISO, "cenários C e D", "indisponíveis com a integração atual",
          "a sessão web envia só texto (app/llm_session.py:245 monta o pedido "
          "como uma string). Ouvir o áudio exigiria API paga ou mexer em "
          "produção — fora do escopo. A matriz mostra a lacuna.")


def _sessao_ia(r: Relato) -> None:
    """O planejador de cortes usa a mesma sessão web."""
    try:
        from app.llm_gateway import status

        if status().get("ok"):
            r.add(OK, "planejador (--cortes)", "sessão pronta")
        else:
            r.add(AVISO, "planejador (--cortes)", "sem sessão",
                  "a linha de divergência do plano sai como 'sem dado'")
    except Exception as e:  # noqa: BLE001
        r.add(AVISO, "planejador (--cortes)", f"{type(e).__name__}: {e}")


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
        r.add(OK, "duração total", f"{duracao / 60:.1f} min de áudio")
        _previsao(r, duracao / 60)


def _previsao(r: Relato, minutos: float) -> None:
    """Quanto a rodada vai custar e demorar, ANTES de começar.

    Cota de API se gasta uma vez. Ver o número antes é a diferença entre
    decidir rodar 8 vídeos e descobrir depois que deu para 3.
    """
    if minutos <= 0:
        return
    p = Path(__file__).resolve().parent / "custos.json"
    precos = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

    total, sem_preco = 0.0, []
    # Só o Scribe cobra por API neste benchmark: o Gemini roda pela sessão web
    # do usuário, e o Whisper é local. C e D estão indisponíveis.
    for motor in ("scribe",):
        v = (precos.get(motor) or {}).get("usd_por_minuto_de_audio")
        if v is None:
            sem_preco.append(motor)
        else:
            total += float(v) * minutos

    if sem_preco:
        r.add(AVISO, "gasto previsto",
              f"não dá para calcular: sem preço de {', '.join(sem_preco)}",
              "preencha custos.json — a rodada gasta cota de verdade e vale "
              "saber quanto antes")
    else:
        r.add(OK, "gasto previsto",
              f"~US$ {total:.2f} para {minutos:.1f} min de áudio "
              f"(só o Scribe cobra; Gemini via sessão web e Whisper local "
              f"não geram custo de API)")

    # Tempo: B é medido (2,7x tempo real em GPU, ~1x em CPU); nuvem varia.
    try:
        from app.transcricao.plataforma import detectar

        fator = 2.7 if detectar().backend == "cuda" else 0.9
    except Exception:  # noqa: BLE001
        fator = 0.9
    r.add(OK, "tempo previsto",
          f"cenário B ~{minutos / fator:.0f} min; A soma upload e espera do "
          f"Scribe, E soma a ida ao Gemini por cima",
          "a rodada retoma de onde parou — se cair, rode o mesmo comando de "
          "novo sem --refazer")


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
