# -*- coding: utf-8 -*-
"""Uma operação só: preflight → benchmark → preliminar → (humano) → relatório.

    python tools/bench_transcricao/benchmark.py --corpus corpus.json

Não reimplementa nada: chama o `main()` de cada etapa, as mesmas que rodam
sozinhas. Se uma etapa mudar, esta muda junto por construção.

O fluxo PARA na validação humana, de propósito. Ninguém escolhe arquitetura de
produção sem alguém ter ouvido o áudio, e o relatório final não roda até a
referência existir. Depois de validar, rode o mesmo comando: as etapas já
concluídas são reaproveitadas e ele segue direto para a matriz.

Códigos de saída:
    0  matriz final impressa
    1  rodou e parou na validação humana (esperado na primeira vez)
    2  preflight barrou: falta o que o benchmark não roda sem
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _etapa(titulo: str) -> None:
    print(f"\n{'=' * 72}\n{titulo}\n{'=' * 72}")


def _chamar(modulo, argv: list[str]) -> int:
    """Roda o main() da etapa com argv próprio, sem subprocesso."""
    antigo = sys.argv
    sys.argv = [modulo.__name__, *argv]
    try:
        return int(modulo.main() or 0)
    finally:
        sys.argv = antigo


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark de transcrição do ATIVAVID, ponta a ponta")
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--saida", default="bench")
    ap.add_argument("--modelo", default="medium")
    ap.add_argument("--sem-cortes", action="store_true",
                    help="pular o planejamento de cortes (não exige sessão de IA)")
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--ignorar-preflight", action="store_true",
                    help="rodar mesmo com o preflight barrando (não recomendado)")
    a = ap.parse_args()

    from tools.bench_transcricao import (preflight, preliminar, relatorio,
                                         rodar)

    _etapa("1/4  PREFLIGHT — o que falta antes de gastar GPU e cota")
    codigo = _chamar(preflight, ["--corpus", a.corpus, "--modelo", a.modelo])
    if codigo >= 2 and not a.ignorar_preflight:
        print("\nParado no preflight. Conserte o que ele apontou e rode de novo.")
        return 2

    _etapa("2/4  BENCHMARK — os cinco cenários")
    argv = ["--corpus", a.corpus, "--saida", a.saida, "--modelo", a.modelo]
    if not a.sem_cortes:
        argv.append("--cortes")
    if a.refazer:
        argv.append("--refazer")
    _chamar(rodar, argv)

    _etapa("3/4  PRELIMINAR — o que já dá para saber sem ouvido humano")
    _chamar(preliminar, ["--saida", a.saida])

    _etapa("4/4  RELATÓRIO FINAL — exige a referência humana")
    codigo = _chamar(relatorio, ["--saida", a.saida])
    if codigo == 0:
        return 0

    val = Path(a.saida) / "validacao"
    print(f"""
O relatório final ainda não roda: falta a referência humana. Isso é o
esperado na primeira passada.

  1. Abra os arquivos validar_*.html em {val}
  2. Ouça cada trecho e marque o que a pessoa REALMENTE falou
     (a página cronometra — trabalhe no ritmo normal; esse relógio é a
      medida de retrabalho real do benchmark)
  3. Clique em "Baixar decisões" e salve o JSON de volta em {val}
  4. Rode este mesmo comando outra vez — as etapas já feitas são
     reaproveitadas e ele segue direto para a matriz

Ninguém escolhe arquitetura de produção sem alguém ter ouvido o áudio.""")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
