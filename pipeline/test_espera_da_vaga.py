# -*- coding: utf-8 -*-
"""A vaga do OVERLAY passou a esperar em vez de desistir na hora.

Medido nos 128 jobs reais: a vaga fica ocupada durante 150s de um job de 575s
— 26% dele. E 28% dos jobs foram para o Remotion inteiro sem motivo de recurso
nenhum. Os dois números batem: quem chegava durante a janela do outro perdia a
corrida e pagava o caminho lento.

O preço de cada opção, controlado pela duração do corte:
  esperar ..... no máximo 150s, em média ~75s
  cair ........ +294s (1,91x contra 1,31x de rodar acompanhado)

Esperar é cerca de 4x mais barato. O teto de 180s garante que, no pior caso, o
job perde a espera — nunca o job.

O que estes testes travam: a exclusividade continua de pé (duas vagas ao mesmo
tempo estragariam o motivo de a trava existir), a espera é limitada de verdade,
e quem espera consegue a vaga quando ela é liberada.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def vaga(tmp_path, monkeypatch):
    """Trava isolada: o teste nunca disputa a vaga real do app."""
    from app import overlay_canary as oc

    monkeypatch.setattr(oc, "LOCK_PATH", tmp_path / "overlay-heavy.lock")
    return oc


def test_a_vaga_continua_exclusiva(vaga):
    """A razão de a trava existir: dois OVERLAY pesados juntos disputam a GPU."""
    a = vaga.try_acquire_overlay_slot(espera_s=0)
    assert a is not None
    assert vaga.try_acquire_overlay_slot(espera_s=0) is None, "duas vagas ao mesmo tempo"
    vaga.release_overlay_slot(a)
    b = vaga.try_acquire_overlay_slot(espera_s=0)
    assert b is not None, "a vaga não voltou depois de liberada"
    vaga.release_overlay_slot(b)


def test_quem_espera_pega_a_vaga_quando_ela_sai(vaga):
    """O caso que motivou a mudança: chegar durante a janela do outro."""
    primeiro = vaga.try_acquire_overlay_slot(espera_s=0)
    assert primeiro is not None

    def soltar_depois():
        time.sleep(0.5)
        vaga.release_overlay_slot(primeiro)

    threading.Thread(target=soltar_depois, daemon=True).start()
    t0 = time.monotonic()
    segundo = vaga.try_acquire_overlay_slot(espera_s=10)
    dt = time.monotonic() - t0
    assert segundo is not None, "esperou e mesmo assim não pegou a vaga"
    assert dt >= 0.4, "pegou antes de o outro soltar — a trava não estava valendo"
    assert dt < 8, f"demorou {dt:.1f}s para notar que a vaga saiu"
    vaga.release_overlay_slot(segundo)


def test_a_espera_tem_teto(vaga):
    """Sem teto, um job travado prenderia a fila inteira."""
    preso = vaga.try_acquire_overlay_slot(espera_s=0)
    assert preso is not None
    t0 = time.monotonic()
    assert vaga.try_acquire_overlay_slot(espera_s=1.0) is None
    dt = time.monotonic() - t0
    assert 0.8 <= dt < 6, f"o teto de 1s não foi respeitado ({dt:.1f}s)"
    vaga.release_overlay_slot(preso)


def test_o_padrao_espera(vaga):
    """Chamar sem argumento tem que esperar — o caminho do pipeline é esse."""
    import inspect

    padrao = inspect.signature(vaga.try_acquire_overlay_slot).parameters["espera_s"].default
    assert padrao >= 60, "o padrão precisa cobrir a janela medida (150s de vaga)"
    assert padrao <= 600, "espera longa demais prenderia a fila"
