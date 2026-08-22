# -*- coding: utf-8 -*-
"""Canário da revisão textual. Valida integração, cache, timestamps e rollback.

NÃO é benchmark de qualidade e não mede WER. Não decide nada sobre motor. O
que ele responde é uma pergunta só: os commits 1-5 se comportam na máquina
real como se comportaram nos testes?

    uv run python tools/canario_revisao.py VIDEO1 VIDEO2 VIDEO3

VIDEO1 é o que passa pelos quatro estados (frio → repete → desliga → religa).
VIDEO2 e VIDEO3 levam uma execução com a revisão ligada.

## O que ele NÃO toca

**O cache de produção.** `ATIVAVID_TRANSCRIPT_CACHE` é redirecionado para uma
pasta descartável ANTES de `transcribe` ser importado — `CACHE_ENTRE_PROJETOS`
é resolvido no import, e definir a variável depois não tem efeito nenhum
(erro que já custou uma rodada deste projeto).

**Seus projetos.** Cada vídeo roda num `edit-dir` temporário.

**O Scribe.** `transcribe_one` é chamado com `backend="local"`, `api_key=""` e
`elevenlabs_key=None`. Não existe caminho para o motor pago daqui, e o
canário ainda confere isso no fim.

**O padrão.** `ATIVAVID_REVISAO` é definido por passo, em memória. O padrão
gravado no código continua `off`.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# ANTES de qualquer import do projeto: cache isolado.
CACHE = Path(tempfile.mkdtemp(prefix="canario-cache-"))
os.environ["ATIVAVID_TRANSCRIPT_CACHE"] = str(CACHE)
os.environ.pop("ATIVAVID_REVISAO", None)
# ---------------------------------------------------------------------------

for extra in (RAIZ, RAIZ / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

import transcribe as tr                                      # noqa: E402
from app.transcricao import revisao                          # noqa: E402

assert tr.CACHE_ENTRE_PROJETOS == CACHE, (
    "o redirecionamento do cache não pegou — abortando para não escrever no "
    "cache de produção")


# ------------------------------------------------------------- instrumentação

class Contador:
    """Conta chamadas reais. Não substitui nada: envolve e repassa."""

    def __init__(self) -> None:
        self.whisper = 0
        self.gemini = 0
        self.falhar = False
        self._instalar()

    def _instalar(self) -> None:
        from app.transcricao import whisper_local

        original_motor = whisper_local.MotorWhisperLocal.transcrever
        contador = self

        def transcrever(self, *a, **k):
            contador.whisper += 1
            return original_motor(self, *a, **k)

        whisper_local.MotorWhisperLocal.transcrever = transcrever

        original_gemini = revisao.pedir_correcoes

        def pedir(palavras, texto):
            contador.gemini += 1
            if contador.falhar:
                # Falha injetada. Exercita o caminho de erro REAL
                # (`revisar` → `_revisar_payload` → marca → cache) sem
                # derrubar a sessão do usuário nem gastar um centavo.
                raise revisao.RevisaoIndisponivel(
                    "FALHA INJETADA PELO CANÁRIO: sessão indisponível")
            return original_gemini(palavras, texto)

        revisao.pedir_correcoes = pedir

    def zerar(self) -> None:
        self.whisper = self.gemini = 0


CONTA = Contador()
MARCADORES = ("REVISAO_GEMINI", "REVISAO_GEMINI_PULADA",
              "REVISAO_GEMINI_FALHOU", "TRANSCRIPTION CACHE HIT",
              "ELEVENLABS_FALHOU", "WHISPER_", "PRIMEIRO_USO")


class Passo:
    """O resultado de uma execução: payload, marcadores, contadores, tempo."""

    def __init__(self, rotulo: str) -> None:
        self.rotulo = rotulo
        self.payload: dict = {}
        self.linhas: list[str] = []
        self.whisper = self.gemini = 0
        self.seg = 0.0
        self.marca = ""
        self.erro = ""

    @property
    def texto(self) -> str:
        return str(self.payload.get("text") or "")

    @property
    def tempos(self) -> list[tuple[float, float]]:
        return [(w["start"], w["end"]) for w in self.payload.get("words") or []
                if w.get("type") == "word"]

    def marcador(self, prefixo: str) -> str:
        for l in self.linhas:
            if l.startswith(prefixo):
                return l
        return ""

    def campo(self, chave: str) -> str:
        """Lê `chave=valor` da linha `REVISAO_GEMINI ok`."""
        for l in self.linhas:
            for parte in l.split():
                if parte.startswith(f"{chave}="):
                    return parte.split("=", 1)[1]
        return ""


def rodar(rotulo: str, video: Path, edit: Path, modo_revisao: str) -> Passo:
    p = Passo(rotulo)
    os.environ["ATIVAVID_REVISAO"] = modo_revisao
    CONTA.zerar()
    buf = io.StringIO()
    t0 = time.perf_counter()
    try:
        with contextlib.redirect_stdout(buf):
            saida = tr.transcribe_one(
                video, edit, api_key="", language="pt", backend="local",
                verbose=True, elevenlabs_key=None)
        p.payload = json.loads(Path(saida).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        p.erro = f"{type(e).__name__}: {e}"
    p.seg = time.perf_counter() - t0
    p.whisper, p.gemini = CONTA.whisper, CONTA.gemini
    p.linhas = [l.rstrip() for l in buf.getvalue().splitlines()
                if any(m in l for m in MARCADORES)]
    p.marca = tr.marca_da_assinatura(edit / "transcripts", video.stem) or ""

    print(f"\n{'=' * 74}\n{rotulo}   [ATIVAVID_REVISAO={modo_revisao}]\n{'=' * 74}")
    for l in p.linhas:
        print(f"  | {l}")
    if not p.linhas:
        print("  | (nenhum marcador)")
    print(f"  whisper={p.whisper}  gemini={p.gemini}  "
          f"marca={p.marca or '(sem)'}  {p.seg:.1f}s")
    if p.erro:
        print(f"  ERRO: {p.erro}")
    return p


# ----------------------------------------------------------------- verificação

RESULTADOS: list[tuple[str, str, bool, str]] = []


def checar(cenario: str, criterio: str, ok: bool, detalhe: str = "") -> None:
    RESULTADOS.append((cenario, criterio, bool(ok), detalhe))
    print(f"    [{'PASS' if ok else 'FAIL'}] {criterio}"
          + (f"  — {detalhe}" if detalhe else ""))


def hit_do_projeto(edit: Path, video: Path, modo_revisao: str) -> bool:
    """`transcript_cache_hit` aceitaria o transcript que está no projeto?

    Perguntado DIRETO, e não deduzido do texto que saiu. Se o Gemini não
    propuser nada num vídeo, o texto revisado é igual ao puro e comparar
    texto não prova nada — mas a marca e esta resposta provam.
    """
    os.environ["ATIVAVID_REVISAO"] = modo_revisao
    return tr.transcript_cache_hit(edit / "transcripts" / f"{video.stem}.json",
                                   video)


def marcas_no_cache() -> list[str]:
    return sorted(p.name.split(".", 1)[1].removesuffix(".json")
                  for p in CACHE.glob("*.json"))


def karaoke(payload: dict, edit: Path, stem: str) -> tuple[bool, str]:
    """As legendas saem do transcript sem defeito temporal?

    Roda o MESMO `captions_from_transcript` que o pipeline usa, e cobra os
    invariantes que um timestamp corrompido quebraria: início crescente,
    duração positiva, e nenhuma palavra que o `_word_items` precise mover
    além do que ele já moveria no transcript puro.
    """
    from captions_for_remotion import _word_items, captions_from_transcript

    caminho = edit / "transcripts" / f"{stem}.json"
    caps = captions_from_transcript(caminho)
    if not caps:
        return False, "nenhuma legenda gerada"
    for a, b in zip(caps, caps[1:]):
        if b["startMs"] < a["startMs"]:
            return False, f"legenda fora de ordem em {a['startMs']}ms"
    if any(c["endMs"] <= c["startMs"] for c in caps):
        return False, "legenda com duração <= 0"

    cru = [w for w in (payload.get("words") or []) if w.get("type") == "word"]
    itens = _word_items(payload)
    reparadas = sum(1 for w, i in zip(cru, itens)
                    if abs(float(w["start"]) - i["start"]) > 1e-9)
    return True, f"{len(caps)} legendas, {reparadas} palavra(s) reparada(s)"


def sem_scribe(p: Passo) -> tuple[bool, str]:
    if p.marcador("ELEVENLABS_FALHOU"):
        return False, "marcador do ElevenLabs apareceu"
    motor = str(p.payload.get("_motor") or "")
    if motor and "whisper" not in motor.lower():
        return False, f"_motor={motor}"
    sujas = [m for m in marcas_no_cache() if not m.startswith("local-")]
    if sujas:
        return False, f"cache com marca de outro motor: {sujas}"
    return True, f"_motor={motor or '(vazio)'}"


# ----------------------------------------------------------------------- fluxo

def main() -> int:
    videos = [Path(a).expanduser().resolve() for a in sys.argv[1:4]]
    if len(videos) != 3:
        print(__doc__)
        return 2
    for v in videos:
        if not v.is_file():
            print(f"não encontrei: {v}")
            return 2

    trabalho = Path(tempfile.mkdtemp(prefix="canario-"))
    print(f"cache isolado : {CACHE}")
    print(f"trabalho      : {trabalho}")
    print(f"padrão gravado: {revisao.PADRAO}  (não foi alterado)")

    # ------------------------------------------------ VÍDEO 1, os quatro estados
    v1 = videos[0]
    e1 = trabalho / "v1"
    e1.mkdir(parents=True)

    p1 = rodar("1. revisão LIGADA, cache frio para +rev1", v1, e1, "gemini")
    modelo = p1.marca.removeprefix("local-").removesuffix(revisao.SUFIXO)
    checar("1", "job terminou sem erro", not p1.erro, p1.erro)
    checar("1", "Whisper/local executou", p1.whisper == 1, f"{p1.whisper}x")
    checar("1", "Gemini chamado uma vez", p1.gemini == 1, f"{p1.gemini}x")
    checar("1", "REVISAO_GEMINI ok", p1.marcador("REVISAO_GEMINI ok") != "",
           p1.marcador("REVISAO_GEMINI ok"))
    checar("1", "ts_preservados verdadeiro",
           p1.campo("ts_preservados") == "True", p1.campo("ts_preservados"))
    checar("1", f"marca local-{modelo}+rev1",
           p1.marca == f"local-{modelo}{revisao.SUFIXO}", p1.marca)
    checar("1", "cache puro preservado ao lado do revisado",
           marcas_no_cache() == sorted([f"local-{modelo}-{modelo}",
                                        f"local-{modelo}{revisao.SUFIXO}-{modelo}"]),
           str(marcas_no_cache()))
    ok, det = karaoke(p1.payload, e1, v1.stem)
    checar("1", "legenda/karaokê sem defeito temporal", ok, det)
    ok, det = sem_scribe(p1)
    checar("1", "nenhum fallback para Scribe", ok, det)

    aceita_revisado = hit_do_projeto(e1, v1, "gemini")
    p2 = rodar("2. revisão LIGADA de novo", v1, e1, "gemini")
    # O transcript revisado JÁ está no projeto, então `transcript_cache_hit`
    # aceita e o job devolve na hora — sem chegar ao cache entre projetos e
    # sem imprimir marcador. Um hit em `+rev1` lá também vale (é o que
    # acontece num projeto novo com a mesma fonte).
    checar("2", "hit em +rev1",
           aceita_revisado and p2.marca.endswith(revisao.SUFIXO),
           f"cache do projeto aceitou={aceita_revisado} marca={p2.marca}"
           + (f" | {p2.marcador('TRANSCRIPTION CACHE HIT')}" if p2.linhas else ""))
    checar("2", "Whisper não rodou", p2.whisper == 0, f"{p2.whisper}x")
    checar("2", "Gemini não rodou", p2.gemini == 0, f"{p2.gemini}x")
    checar("2", "texto idêntico à passada 1", p2.texto == p1.texto)
    checar("2", "timestamps idênticos à passada 1", p2.tempos == p1.tempos)

    recusado = not hit_do_projeto(e1, v1, "off")
    p3 = rodar("3. revisão DESLIGADA", v1, e1, "off")
    checar("3", "transcript +rev1 não foi aceito como puro", recusado,
           "transcript_cache_hit devolveu False com a revisão desligada")
    checar("3", "recuperou a variante Whisper pura",
           p3.marca == f"local-{modelo}" and "_revisao" not in p3.payload,
           f"marca={p3.marca}, campo _revisao "
           f"{'ausente' if '_revisao' not in p3.payload else 'PRESENTE'}")
    checar("3", "Gemini não foi chamado", p3.gemini == 0, f"{p3.gemini}x")
    checar("3", "não retranscreveu o áudio", p3.whisper == 0, f"{p3.whisper}x")
    checar("3", "nada precisou ser apagado à mão",
           marcas_no_cache() == sorted([f"local-{modelo}-{modelo}",
                                        f"local-{modelo}{revisao.SUFIXO}-{modelo}"]),
           "as duas variantes continuam no cache")

    p4 = rodar("4. revisão RELIGADA", v1, e1, "gemini")
    checar("4", "voltou a encontrar +rev1",
           p4.marca == f"local-{modelo}{revisao.SUFIXO}"
           and p4.payload.get("_revisao") == revisao.VERSAO,
           f"marca={p4.marca} _revisao={p4.payload.get('_revisao')}")
    checar("4", "Gemini não foi chamado de novo", p4.gemini == 0, f"{p4.gemini}x")
    checar("4", "Whisper não foi chamado de novo", p4.whisper == 0, f"{p4.whisper}x")
    checar("4", "texto idêntico à passada 1", p4.texto == p1.texto)
    checar("4", "timestamps idênticos à passada 1", p4.tempos == p1.tempos)

    # ------------------------------------------------------ VÍDEOS 2 e 3
    for n, v in ((2, videos[1]), (3, videos[2])):
        e = trabalho / f"v{n + 1}"
        e.mkdir(parents=True)
        c = f"V{n}"
        p = rodar(f"{c}. {v.name} — execução única, revisão LIGADA",
                  v, e, "gemini")
        checar(c, "job terminou sem erro", not p.erro, p.erro)
        checar(c, "REVISAO_GEMINI ok", p.marcador("REVISAO_GEMINI ok") != "",
               p.marcador("REVISAO_GEMINI ok"))
        checar(c, "ts_preservados verdadeiro",
               p.campo("ts_preservados") == "True", p.campo("ts_preservados"))
        esperado = {"words", "text", "language_code", "_motor", "_modelo",
                    "_backend"}
        checar(c, "schema sem regressão",
               esperado <= set(p.payload) and all(
                   set(w) >= {"text", "start", "end", "type", "speaker_id"}
                   for w in p.payload.get("words") or []),
               f"chaves: {sorted(set(p.payload) - esperado)}")
        ok, det = karaoke(p.payload, e, v.stem)
        checar(c, "legenda correta e karaokê sincronizado", ok, det)
        ok, det = sem_scribe(p)
        checar(c, "nenhum fallback para Scribe", ok, det)
        prop, apl, ign = (p.campo("correcoes"), "", p.campo("ignoradas"))
        aplicadas, propostas = (prop.split("/") + [""])[:2]
        coerente = (aplicadas.isdigit() and propostas.isdigit()
                    and ign.isdigit()
                    and int(aplicadas) + int(ign) <= int(propostas))
        checar(c, "proposta/aplicada/ignorada coerente", coerente,
               f"aplicadas={aplicadas} ignoradas={ign} de {propostas}")
        checar(c, "tempo adicional da revisão registrado",
               p.campo("seg") not in ("", "None"),
               f"revisão {p.campo('seg')}s de {p.seg:.1f}s totais")

    # ----------------------------------------------- falha controlada do Gemini
    v5 = videos[1]
    e5 = trabalho / "falha"
    e5.mkdir(parents=True)
    # Cache frio para este vídeo nesta pasta: queremos o caminho completo.
    for p_ in CACHE.glob("*.json"):
        if tr.chave_da_fonte(v5) in p_.name:
            p_.unlink()

    CONTA.falhar = True
    pf = rodar("F. Gemini indisponível (falha injetada)", v5, e5, "gemini")
    CONTA.falhar = False
    checar("F", "job terminou sem erro", not pf.erro, pf.erro)
    checar("F", "REVISAO_GEMINI_FALHOU", pf.marcador("REVISAO_GEMINI_FALHOU") != "",
           pf.marcador("REVISAO_GEMINI_FALHOU"))
    checar("F", "terminou com Whisper puro",
           bool(pf.payload.get("words")) and "_revisao" not in pf.payload,
           f"{len(pf.tempos)} palavras, sem campo _revisao")
    checar("F", "NÃO gravou +rev1 na assinatura",
           pf.marca and revisao.SUFIXO not in pf.marca, pf.marca)
    checar("F", "NÃO gravou +rev1 no cache",
           not any(revisao.SUFIXO in m and tr.chave_da_fonte(v5)
                   in "".join(x.name for x in CACHE.glob("*.json") if m in x.name)
                   for m in marcas_no_cache()),
           str(marcas_no_cache()))
    ok, det = sem_scribe(pf)
    checar("F", "não caiu para o Scribe", ok, det)

    pg = rodar("F2. Gemini restaurado", v5, e5, "gemini")
    checar("F2", "tentou revisar de novo", pg.gemini == 1, f"{pg.gemini}x")
    checar("F2", "não retranscreveu", pg.whisper == 0, f"{pg.whisper}x")
    checar("F2", "agora sim gravou +rev1",
           revisao.SUFIXO in pg.marca, pg.marca)

    # ------------------------------------------------------------------ tabela
    print(f"\n\n{'=' * 74}\nTABELA\n{'=' * 74}")
    print(f"{'cenário':<8}{'critério':<52}{'':<4}resultado")
    print("-" * 74)
    for cen, crit, ok, det in RESULTADOS:
        print(f"{cen:<8}{crit[:50]:<52}{'':<4}{'PASS' if ok else 'FAIL'}")
    falhas = [r for r in RESULTADOS if not r[2]]
    print("-" * 74)
    print(f"{len(RESULTADOS) - len(falhas)} PASS   {len(falhas)} FAIL")
    if falhas:
        print("\nFALHAS:")
        for cen, crit, _, det in falhas:
            print(f"  {cen}  {crit}  — {det}")

    print(f"\n\n{'=' * 74}\nMARCADORES REAIS DO PIPELINE\n{'=' * 74}")
    for p in (p1, p2, p3, p4, pf, pg):
        print(f"\n[{p.rotulo}]")
        for l in p.linhas:
            print(f"  {l}")

    print(f"\n\nfalta conferir a olho: abra o projeto do vídeo do karaokê e "
          f"veja a legenda acendendo.\ntrabalho preservado em {trabalho}")
    print(f"apague quando terminar:  {CACHE}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
