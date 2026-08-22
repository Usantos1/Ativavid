# -*- coding: utf-8 -*-
"""Quanto o transcript muda a edição final e a legenda.

Duas perguntas do pedido que não se respondem olhando texto:

  **cortes** — o mesmo material, planejado a partir de cada transcript, dá o
  mesmo vídeo? Roda `helpers/pack_transcripts.py` → `helpers/llm_cut_plan.py`,
  os módulos de produção, e compara nº de cortes, duração final e sobreposição
  dos trechos escolhidos. Não se espera resultado idêntico; a pergunta é
  QUANTO o transcript influencia.

  **karaokê** — a legenda gerada sobrevive aos invariantes que o
  `tools/conferir_legendas.py` cobra dos projetos reais? Usa
  `helpers/captions_for_remotion.py` para produzir as cues de verdade e checa
  as mesmas propriedades: nada duplicado, ordem da fala, duração > 0, nada
  inventado, nenhuma cue vazia.

Precisa de sessão de IA ativa (a mesma que o 1-clique usa) para a parte de
cortes. Sem ela, a parte de karaokê roda sozinha e a de cortes fica `None` —
que o relatório mostra como "sem dado".
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
for extra in (RAIZ, RAIZ / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.transcricao import Palavra          # noqa: E402
from tools.bench_transcricao.motores import Saida   # noqa: E402


# ------------------------------------------------------------------- karaokê

@dataclass
class Karaoke:
    """O que a legenda precisou que a produção consertasse.

    A descoberta que define esta métrica: `captions_for_remotion._word_items`
    NÃO quebra com transcript ruim — ele REPARA. Força `start` crescente
    (+1 ms) e duração mínima de 40 ms, porque 133 dos 178 transcripts do
    usuário tinham palavra voltando no tempo.

    Então a pergunta certa não é "o karaokê quebra?", e sim "quanto a produção
    teve de mexer?". Cada milissegundo de reparo é uma palavra saindo de cima
    do áudio: na tela continua bonito, e acende fora da hora. É exatamente o
    que o cenário D não pode causar.
    """

    cues: int = 0
    # Defeitos no que o MOTOR entregou, antes de qualquer conserto.
    duplicadas: int = 0
    fora_de_ordem: int = 0
    duracao_invalida: int = 0
    vazias: int = 0
    palavra_curta: int = 0
    sobreposicoes: int = 0
    # Quanto a produção teve de deslocar para a legenda ficar renderizável.
    palavras_reparadas: int = 0
    deslocamento_total_ms: float = 0.0
    deslocamento_maximo_ms: float = 0.0
    problemas: list[str] = field(default_factory=list)

    @property
    def intacto(self) -> bool:
        """A produção não precisou mexer em nada."""
        return self.palavras_reparadas == 0

    @property
    def aprovado(self) -> bool:
        """Nenhum defeito estrutural no que o motor entregou."""
        return not (self.duplicadas or self.fora_de_ordem
                    or self.duracao_invalida or self.vazias)


def cues_de(saida: Saida) -> list[dict]:
    """Gera as cues com o módulo de produção, a partir do schema do Scribe."""
    from captions_for_remotion import _pack, _word_items

    bruto = {"words": [{"text": p.texto, "start": p.inicio, "end": p.fim,
                        "type": "word", "speaker_id": "speaker_0"}
                       for p in saida.palavras]}
    return [_pack(w["text"], float(w["start"]), float(w["end"]))
            for w in _word_items(bruto)]


def conferir_karaoke(saida: Saida) -> Karaoke:
    if saida.granularidade != "palavra" or not saida.palavras:
        k = Karaoke()
        k.problemas.append(
            f"granularidade '{saida.granularidade}': não há legenda karaokê "
            f"para conferir")
        return k

    k = Karaoke(cues=len(saida.palavras))

    # 1. Defeitos no que o motor entregou.
    visto: dict[tuple, int] = {}
    anterior = None
    for p in saida.palavras:
        texto = p.texto.strip()
        if not texto:
            k.vazias += 1
        chave = (texto.casefold(), round(p.inicio, 1))
        visto[chave] = visto.get(chave, 0) + 1
        if visto[chave] > 1:
            k.duplicadas += 1
            k.problemas.append(f"{texto!r} repetida em {p.inicio:.2f}s")
        if anterior is not None and p.inicio < anterior.inicio - 1e-6:
            k.fora_de_ordem += 1
            k.problemas.append(f"{texto!r} volta no tempo em {p.inicio:.2f}s")
        if anterior is not None and p.inicio < anterior.fim - 1e-6:
            k.sobreposicoes += 1
        if p.fim - p.inicio <= 0:
            k.duracao_invalida += 1
            k.problemas.append(f"{texto!r} com duração "
                               f"{(p.fim - p.inicio) * 1000:.0f} ms")
        elif p.fim - p.inicio < 0.12:
            k.palavra_curta += 1
        anterior = p

    # 2. Quanto a produção teve de reparar.
    for p, c in zip(saida.palavras, cues_de(saida)):
        d = abs(c["startMs"] - p.inicio * 1000)
        if d > 0.5:                      # meio ms: ruído de arredondamento
            k.palavras_reparadas += 1
            k.deslocamento_total_ms += d
            k.deslocamento_maximo_ms = max(k.deslocamento_maximo_ms, d)
    if k.palavras_reparadas:
        k.problemas.append(
            f"a produção deslocou {k.palavras_reparadas} palavra(s) para a "
            f"legenda ficar renderizável (pior: "
            f"{k.deslocamento_maximo_ms:.0f} ms fora do áudio)")
    return k


# -------------------------------------------------------------------- cortes

@dataclass
class Cortes:
    n: int = 0
    duracao_s: float = 0.0
    trechos: list[tuple[float, float]] = field(default_factory=list)
    erro: str = ""


def _escrever_edit_dir(saida: Saida, video: Path, destino: Path) -> Path:
    """Monta um edit_dir mínimo com o transcript deste motor."""
    t = destino / "transcripts"
    t.mkdir(parents=True, exist_ok=True)
    (t / f"{video.stem}.json").write_text(json.dumps({
        "words": [{"text": p.texto, "start": p.inicio, "end": p.fim,
                   "type": "word", "speaker_id": "speaker_0"}
                  for p in saida.palavras],
        "text": saida.texto, "language_code": "por",
    }, ensure_ascii=False), encoding="utf-8")
    return destino


def planejar(saida: Saida, video: Path, destino: Path,
             preset: dict | None = None) -> Cortes:
    """Roda o planejador de produção sobre este transcript."""
    from llm_cut_plan import plan_cut
    from pack_transcripts import pack_one_file, render_markdown
    from speech_regions import speech_regions

    if not saida.palavras:
        return Cortes(erro="motor sem palavras")

    edit = _escrever_edit_dir(saida, video, destino)
    tj = edit / "transcripts" / f"{video.stem}.json"
    entrada = pack_one_file(tj, silence_threshold=0.35)
    (edit / "takes_packed.md").write_text(
        render_markdown([entrada], 0.35), encoding="utf-8")

    try:
        regioes = speech_regions(video, "-33dB", 0.10)
        trechos, _meta = plan_cut(
            edit_dir=edit, source_key=video.stem,
            preset=preset or {"edit": "limpa"}, regions=regioes,
            voice={}, duration_s=None)
    except Exception as e:  # noqa: BLE001
        return Cortes(erro=f"{type(e).__name__}: {e}")

    faixas = [(float(r["start"]), float(r["end"])) for r in trechos]
    return Cortes(n=len(faixas),
                  duracao_s=round(sum(b - a for a, b in faixas), 3),
                  trechos=faixas)


def sobreposicao_de_planos(a: Cortes, b: Cortes) -> float:
    """Fração do tempo do plano A que também está no plano B.

    1.0 = os dois transcripts levaram ao MESMO vídeo. É a medida que responde
    "quanto o transcript influencia a edição final" sem exigir que sejam iguais.
    """
    if not a.trechos or not b.trechos:
        return float("nan")
    total = sum(y - x for x, y in a.trechos)
    if total <= 0:
        return float("nan")
    comum = 0.0
    for x, y in a.trechos:
        for u, v in b.trechos:
            comum += max(0.0, min(y, v) - max(x, u))
    return min(comum / total, 1.0)
