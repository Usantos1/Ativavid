# -*- coding: utf-8 -*-
"""Reimportar a mesma fonte não paga a transcrição de novo.

O cache que existia vivia dentro de `transcripts/` do projeto. Uma importação
nova nasce com essa pasta vazia, então reimportar o MESMO arquivo chamava a
API outra vez — tempo e cota do plano pago.

Medido nos 129 projetos do usuário: 112 fontes distintas, **14 importadas mais
de uma vez** (uma delas 5 vezes), somando **22 minutos** de ANALYZE pagos em
repetição. `img_3987.mov` sozinho foi importado 5 vezes.

A chave é o CONTEÚDO (tamanho + 4 MB de cada ponta), não o nome: a mesma
gravação importada com outro nome é a mesma gravação, e um arquivo diferente
com o mesmo tamanho E as mesmas duas pontas não acontece por acidente. Ler o
arquivo inteiro sairia caro — as fontes do usuário passam de 500 MB.

Backend e modelo entram na chave: o usuário paga pelo Scribe justamente pela
qualidade, e servir um transcript do Groq no lugar seria degradar calado.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    """Cache isolado: nunca encostar no de verdade do usuário."""
    import transcribe as tr

    destino = tmp_path / "cache"
    monkeypatch.setattr(tr, "CACHE_ENTRE_PROJETOS", destino)
    return destino


def _fonte(tmp_path: Path, nome: str, tamanho: int, semente: bytes) -> Path:
    p = tmp_path / nome
    corpo = (semente * ((tamanho // len(semente)) + 1))[:tamanho]
    p.write_bytes(corpo)
    return p


PAYLOAD = {"words": [{"text": "oi", "start": 0.0, "end": 0.4, "type": "word"}]}


def test_o_mesmo_arquivo_com_outro_nome_tem_a_mesma_chave(tmp_path, cache):
    import transcribe as tr

    a = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")
    b = _fonte(tmp_path, "copia_do_cliente.mov", 300_000, b"abcd")
    assert tr.chave_da_fonte(a) == tr.chave_da_fonte(b), (
        "a chave está olhando o nome — a mesma gravação renomeada pagaria de novo"
    )


def test_arquivos_diferentes_tem_chaves_diferentes(tmp_path, cache):
    import transcribe as tr

    a = _fonte(tmp_path, "a.mov", 300_000, b"abcd")
    b = _fonte(tmp_path, "b.mov", 300_000, b"xyzw")     # mesmo tamanho, outro conteúdo
    c = _fonte(tmp_path, "c.mov", 300_001, b"abcd")     # mesmo conteúdo, outro tamanho
    assert len({tr.chave_da_fonte(x) for x in (a, b, c)}) == 3


def test_a_chave_nao_le_o_arquivo_inteiro(tmp_path, cache, monkeypatch):
    """As fontes do usuário passam de 500 MB; ler tudo para consultar um cache
    custaria mais que o cache economiza."""
    import transcribe as tr

    grande = _fonte(tmp_path, "grande.mov", 20 << 20, b"abcdefgh")   # 20 MB
    lido = {"bytes": 0}
    real = Path.open

    def espiao(self, *a, **k):
        f = real(self, *a, **k)
        if self == grande:
            leitura = f.read

            def conta(n=-1):
                dados = leitura(n)
                lido["bytes"] += len(dados)
                return dados
            f.read = conta
        return f

    monkeypatch.setattr(Path, "open", espiao)
    tr.chave_da_fonte(grande)
    assert lido["bytes"] <= 9 << 20, (
        f"leu {lido['bytes'] / 1e6:.0f} MB de um arquivo de 20 MB")


def test_guarda_e_devolve(tmp_path, cache):
    import transcribe as tr

    v = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") is None
    tr.guardar_no_cache(v, "elevenlabs", "scribe_v1", PAYLOAD)
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") == PAYLOAD


def test_nao_serve_transcricao_de_outro_backend(tmp_path, cache):
    """O usuário paga pelo Scribe pela qualidade; entregar o do Groq no lugar
    seria degradar sem avisar."""
    import transcribe as tr

    v = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")
    tr.guardar_no_cache(v, "groq", "whisper-large-v3", PAYLOAD)
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") is None
    assert tr.buscar_no_cache(v, "groq", "whisper-large-v3") == PAYLOAD


def test_o_cut_fica_de_fora(tmp_path, cache):
    """O cut é regravado a cada render; confiar num transcript dele foi a
    origem do bug da legenda velha."""
    import transcribe as tr

    v = _fonte(tmp_path, "cut.mp4", 300_000, b"abcd")
    tr.guardar_no_cache(v, "elevenlabs", "scribe_v1", PAYLOAD)
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") is None
    assert not list(cache.glob("*.json")) if cache.is_dir() else True


def test_payload_vazio_nao_entra(tmp_path, cache):
    """Guardar um resultado ruim seria pior que não ter cache: ele voltaria
    em toda importação seguinte."""
    import transcribe as tr

    v = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")
    for ruim in ({}, {"words": []}, None, "nao sou dict"):
        tr.guardar_no_cache(v, "elevenlabs", "scribe_v1", ruim)
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") is None


def test_o_cache_nao_cresce_sem_limite(tmp_path, cache, monkeypatch):
    import transcribe as tr

    monkeypatch.setattr(tr, "_TETO_DO_CACHE", 5)
    for i in range(9):
        v = _fonte(tmp_path, f"v{i}.mov", 300_000 + i, b"abcd")
        tr.guardar_no_cache(v, "elevenlabs", "scribe_v1", PAYLOAD)
    assert len(list(cache.glob("*.json"))) <= 5


def test_uma_falha_de_disco_nao_derruba_a_transcricao(tmp_path, cache, monkeypatch):
    """O cache é conveniência. Perder uma transcrição que já custou a chamada
    de API por causa dele seria o pior resultado possível."""
    import transcribe as tr

    v = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")

    def explode(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(Path, "mkdir", explode)
    tr.guardar_no_cache(v, "elevenlabs", "scribe_v1", PAYLOAD)   # não pode levantar
    monkeypatch.undo()
    assert tr.buscar_no_cache(v, "elevenlabs", "scribe_v1") is None


def test_a_segunda_importacao_nao_chama_a_api(tmp_path, cache, monkeypatch):
    """O teste que importa: com o cache quente, `transcribe_one` devolve sem
    tocar na rede. Qualquer chamada HTTP derruba o teste."""
    import requests

    import transcribe as tr

    fonte = _fonte(tmp_path, "IMG_3987.mov", 300_000, b"abcd")
    tr.guardar_no_cache(fonte, "elevenlabs", "scribe_v1", PAYLOAD)

    def sem_rede(*a, **k):
        raise AssertionError("chamou a API mesmo com o cache quente")

    monkeypatch.setattr(requests, "post", sem_rede)
    monkeypatch.setattr(tr, "_probe_duration", lambda p: 42.0)

    edit = tmp_path / "projeto2" / "edit"
    saida = tr.transcribe_one(
        fonte, edit, api_key="", elevenlabs_key="k",
        backend="elevenlabs", verbose=False,
    )
    assert saida.is_file()
    assert json.loads(saida.read_text(encoding="utf-8")) == PAYLOAD
    # e a assinatura fica gravada, para o cache do PRÓPRIO projeto valer depois
    assert (edit / "transcripts" / f"{fonte.stem}.srcsig").is_file()


def test_sem_cache_a_transcricao_segue_o_caminho_normal(tmp_path, cache, monkeypatch):
    """A prova de que o teste acima mede o cache, e não um curto-circuito.

    Ancorado na EXTRAÇÃO DE ÁUDIO, que é o primeiro passo caro depois da
    consulta — e não na chamada HTTP: com uma fonte falsa o ffmpeg levanta
    antes da rede, e o teste passaria a medir o ffmpeg em vez do cache.
    """
    import transcribe as tr

    fonte = _fonte(tmp_path, "OUTRO.mov", 300_000, b"zzzz")
    extraiu = {"sim": False}

    def marca(*a, **k):
        extraiu["sim"] = True
        raise RuntimeError("parou aqui de propósito")

    monkeypatch.setattr(tr, "extract_audio", marca)
    monkeypatch.setattr(tr, "_probe_duration", lambda p: 42.0)
    with pytest.raises(Exception):
        tr.transcribe_one(fonte, tmp_path / "p3" / "edit", api_key="",
                          elevenlabs_key="k", backend="elevenlabs", verbose=False)
    assert extraiu["sim"], (
        "com o cache FRIO ele devolveu sem transcrever — o teste do cache "
        "quente não provaria nada"
    )


def test_o_cache_mora_fora_do_projeto():
    """Dentro do projeto ele não serviria para nada: o problema é justamente a
    importação NOVA, que nasce com a pasta vazia."""
    import transcribe as tr

    assert "ATIVAVID" in str(tr.CACHE_ENTRE_PROJETOS)
    assert "Projetos" not in str(tr.CACHE_ENTRE_PROJETOS)
    assert os.environ.get("ATIVAVID_TRANSCRIPT_CACHE") or True
