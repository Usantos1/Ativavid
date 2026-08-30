# -*- coding: utf-8 -*-
"""Efeito sonoro escolhido à mão: da Biblioteca até o vídeo.

Pedido do usuário em 29/08: "também adicionar efeitos sonoros ali se a
gente quiser". Até aqui todo efeito era automático — o clique da legenda, o
risco do realce, o whoosh da manchete.

O caminho inteiro, e o que cada teste segura:

* a Biblioteca já guardava efeitos (pasta Efeitos) e o seletor os listava
  como cartão QUEBRADO — tentava mostrar `<img src=...mp3>`;
* escolher um som copiava para `public/library/` e criava um bloco de
  IMAGEM: som que nunca tocaria. Agora vai para `public/sfx/`, que é de
  onde os dois motores tocam;
* o bloco vira `sfxManual` no salvar, e o pipeline só aceita o que existe
  na pasta do projeto (o resto vira aviso no card).
"""
from __future__ import annotations

from pathlib import Path

from app.broll_library import copy_into_public

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_som_vai_para_a_pasta_de_onde_os_motores_tocam(tmp_path):
    (tmp_path / "risada.mp3").write_bytes(b"x")
    r = copy_into_public(tmp_path / "risada.mp3", tmp_path / "public")
    assert r["kind"] == "sfx" and r["src"] == "sfx/risada.mp3"
    assert (tmp_path / "public" / "sfx" / "risada.mp3").exists()


def test_imagem_e_clipe_continuam_na_library(tmp_path):
    for nome, esperado in (("foto.jpg", "image"), ("clipe.mp4", "clip")):
        (tmp_path / nome).write_bytes(b"x")
        r = copy_into_public(tmp_path / nome, tmp_path / "public")
        assert r["kind"] == esperado and r["src"].startswith("library/")


def test_o_seletor_mostra_som_sem_miniatura():
    """Um `<img>` de mp3 é um cartão quebrado — o usuário via um retângulo
    vazio e não sabia que aquilo era um som."""
    assert "it.kind === 'sfx'" in JS
    i = JS.index("it.kind === 'sfx'")
    assert "img-clip-ph som" in JS[i:i + 200]


def test_trilha_nao_entra_como_efeito():
    """Trilha é música de fundo, de minutos: um bloco dela na agulha não é
    um efeito."""
    i = JS.index("if (it.kind === 'track') return;")
    assert i > 0


def test_o_efeito_vira_bloco_de_efeito_e_nao_de_imagem():
    assert "function pushSfxFromRef" in JS
    i = JS.index("function pushSfxFromRef")
    bloco = JS[i:i + 500]
    assert "kind: 'sfx'" in bloco and "isNew: true" in bloco


def test_o_salvar_manda_o_instante_do_efeito():
    """O que importa é o começo: o som toca inteiro a partir dali."""
    i = JS.index("sfxManual: S.insertsDraft")
    bloco = JS[i:i + 260]
    assert "atSec: +c.start.toFixed(3)" in bloco
    assert "volume" in bloco


def test_o_efeito_tem_faixa_propria_na_linha_do_tempo():
    """Misturado com as fotos numa fileira só, o efeito some entre elas."""
    i = JS.index("const isSfx = (c) => c.kind === 'sfx';")
    bloco = JS[i:i + 500]
    assert "icon: 'music'" in bloco
    assert "!isText(c) && !isSfx(c)" in bloco


def test_da_para_ouvir_antes_de_por():
    """O nome do arquivo não diz como o som é: sem ouvir, o usuário só
    descobria que era o errado no vídeo pronto."""
    assert "function ouvirSom" in JS
    i = JS.index("function ouvirSom")
    bloco = JS[i:i + 900]
    # um som por vez: dois juntos viram barulho e não dá para julgar nenhum
    assert "_somOuvindo.pause()" in bloco
    # clicar de novo no mesmo PARA (o botão é play/pause, não só play)
    assert "if (igual) return;" in bloco
    # e toca do próprio projeto, sem copiar nada para lugar nenhum
    assert "/api/library/file?rel=" in JS


def test_o_botao_de_ouvir_nao_insere():
    """Dois alvos, duas ações: o cartão insere, o ▶ só toca. Sem parar a
    propagação, ouvir também colocaria o som na linha do tempo."""
    i = JS.index("img-ouvir')")
    assert "ev.stopPropagation();" in JS[i:i + 300]


def test_a_roda_muda_o_volume_do_efeito():
    """Era fixo em 0,5: som gravado alto entrava alto demais e não havia
    como baixar sem editar arquivo."""
    assert "function somComVolume" in JS
    i = JS.index("function somComVolume")
    bloco = JS[i:i + 900]
    assert "c.volume" in bloco
    assert "Math.max(0.05, Math.min(1.5" in bloco
    assert "1.12" in bloco          # passo multiplicativo
    # o bloco mostra o valor: volume que não se vê é volume que não se ajusta
    assert "%`" in bloco
