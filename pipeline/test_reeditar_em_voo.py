# -*- coding: utf-8 -*-
"""Pedir reedição de um vídeo que ainda está processando.

É o que "Alterar estilo" faz num card em andamento: `/api/jobs/requeue-folder`
chama `worker.cancel(id)` e logo em seguida `worker.enqueue(id)`.

`cancel()` mata o processo e volta na hora — NÃO espera a thread sair de
`_run_one`. Aí o `enqueue()` antigo fazia duas coisas fatais:

  (a) `self._cancel_ids.discard(job_id)` apagava a marca de cancelamento que
      a thread MORIBUNDA ainda ia consultar. Sem a marca, ela tratava a saída
      vazia do processo morto como falha e gravava o job como ERRO.
  (b) `if job_id in self._busy: return` desistia em silêncio, porque a thread
      antiga ainda não tinha soltado o `_busy`. A reedição nunca era
      enfileirada.

Para o usuário: "✓ Estilo salvo — reeditando com o novo visual", e segundos
depois o card com badge ERRO e nada reeditado.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _WorkerFalso:
    """Só as partes de fila do Worker real, com os métodos de verdade."""

    def __init__(self):
        from app.local_server import Worker

        self._proc_lock = threading.RLock()
        self._busy: set[str] = set()
        self._queued: set[str] = set()
        self._cancel_ids: set[str] = set()
        self._refazer_depois: set[str] = set()
        self.posto: list[str] = []
        self.q = type("Q", (), {"put": lambda _s, x: self.posto.append(x)})()
        self.enqueue = Worker.enqueue.__get__(self)


def test_reedicao_pedida_em_voo_nao_se_perde():
    w = _WorkerFalso()
    w._busy.add("job1")           # a thread antiga ainda está em `_run_one`
    w._cancel_ids.add("job1")     # `cancel()` acabou de marcar

    w.enqueue("job1")

    assert "job1" not in w.posto, "não pode rodar dois run_fast no mesmo projeto"
    assert "job1" in w._refazer_depois, "o pedido tem de ficar agendado"
    assert "job1" in w._cancel_ids, "a marca é da thread moribunda, não some"


def test_fora_de_voo_a_marca_de_cancelamento_e_substituida():
    """Cancelou com o job ainda na FILA (nunca começou) e pediu de novo: aí a
    marca é velha e este pedido a substitui, senão `_run_one` desistiria."""
    w = _WorkerFalso()
    w._cancel_ids.add("job2")

    w.enqueue("job2")

    assert "job2" not in w._cancel_ids
    assert w.posto == ["job2"]
    assert "job2" in w._queued


def test_nao_enfileira_duas_vezes():
    w = _WorkerFalso()
    w.enqueue("job3")
    w.enqueue("job3")
    assert w.posto == ["job3"]


def test_o_worker_reenfileira_ao_soltar_o_busy():
    """A outra metade: quem atende o pedido agendado é a thread ao terminar."""
    src = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = src.index("self._busy.discard(job_id)")
    bloco = src[i:i + 900]
    assert "_refazer_depois" in bloco, bloco[:300]
    assert "self.enqueue(job_id)" in bloco, bloco[:600]
