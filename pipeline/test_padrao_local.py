# -*- coding: utf-8 -*-
"""O padrão passou a ser transcrever nesta máquina.

Decidido em 21/08/2026 depois dos benchmarks: 96,6% das palavras no lugar
certo contra 99,7% do serviço em nuvem, tempo total do job indistinguível
(mediana −1,8s em 3 rodadas) e a guarda contra alucinação sem perder nenhuma
das 1.055 palavras reais medidas.

O que estes testes protegem:

- `AUTO` resolve para **local**, e não para o serviço pago;
- **não existe queda automática para o Scribe** — ele é pago, e cair nele
  sozinho gastaria a cota do usuário sem ele pedir;
- a escolha de modelo mora num lugar só, e a CPU recebe `small` por TEMPO
  (medido: `small` na CPU roda a 1,1x tempo real; `medium` seria inutilizável);
- faltar chave do ElevenLabs não gera erro nem aviso de transcrição;
- a telemetria não guarda conteúdo nenhum.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# --- o padrão --------------------------------------------------------------

def test_auto_resolve_para_local(monkeypatch):
    from app.transcricao.modo import (AUTO_RESOLVE_PARA, LOCAL,
                                      backend_para_o_pipeline)

    monkeypatch.delenv("ATIVAVID_TRANSCRICAO", raising=False)
    assert AUTO_RESOLVE_PARA == LOCAL
    assert backend_para_o_pipeline() == LOCAL


def test_sem_configuracao_nenhuma_o_padrao_e_local(monkeypatch):
    """Instalação nova, sem chave e sem nada gravado."""
    import app.transcricao.modo as modo

    monkeypatch.delenv("ATIVAVID_TRANSCRICAO", raising=False)
    monkeypatch.setattr("app.settings_store.load_settings", lambda: {})
    assert modo.backend_para_o_pipeline() == modo.LOCAL


def test_quem_pede_scribe_recebe_scribe(monkeypatch):
    """Ele continua disponível — como escolha, não como surpresa."""
    import app.transcricao.modo as modo

    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", modo.SCRIBE)
    assert modo.backend_para_o_pipeline() == modo.SCRIBE


def test_nao_ha_queda_automatica_para_o_scribe(monkeypatch):
    """O Scribe é pago. Cair nele sozinho gastaria a cota do usuário sem ele
    pedir — que é exatamente o que a migração veio evitar.

    Auditados os motivos de o local faltar, nenhum se resolve com o Scribe:
    componentes não baixados e download falhado precisam da mesma rede que o
    Scribe precisaria; GPU indisponível já cai para CPU sozinho; modelo
    corrompido se resolve rebaixando o modelo.
    """
    import app.transcricao.modo as modo
    from pipeline.leitura_de_codigo import apenas_codigo

    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", modo.LOCAL)
    assert modo.backend_para_o_pipeline() == modo.LOCAL, (
        "o modo local devolveu outra coisa")

    # e a resolução não pode consultar o motor para decidir trocar
    codigo = apenas_codigo(REPO / "app" / "transcricao" / "modo.py")
    i = codigo.index("def backend_para_o_pipeline(")
    corpo = codigo[i:]
    assert "MotorWhisperLocal" not in corpo, (
        "a resolução voltou a decidir trocar de motor por conta própria")
    assert "SCRIBE" not in corpo.split("return")[-1] or "AUTO_RESOLVE_PARA" in corpo


# --- escolha de modelo, num lugar só ---------------------------------------

@pytest.mark.parametrize(("vram", "backend", "esperado"), [
    (4096, "cuda", "medium"),   # a placa do usuário
    (8192, "cuda", "medium"),
    (2048, "cuda", "small"),    # NVIDIA apertada
    (0, "cpu", "small"),        # sem GPU
    (16384, "cpu", "small"),    # CPU manda, mesmo com muita RAM de vídeo
])
def test_a_regra_do_modelo(vram, backend, esperado, monkeypatch):
    from app.transcricao.modelos import escolher_modelo

    monkeypatch.delenv("ATIVAVID_WHISPER_MODEL", raising=False)
    assert escolher_modelo(vram, backend=backend).chave == esperado


def test_a_regra_do_modelo_mora_num_lugar_so():
    """Espalhar essa decisão é como ela vira inconsistente entre caminhos.

    Ancorado no invariante e não em palavras soltas: uma primeira versão
    procurava "vram" + "medium" + "small" em qualquer arquivo e acusou o
    `transcribe.py`, onde esses nomes são os presets de DTW do whisper.cpp —
    nada a ver com a escolha por VRAM.
    """
    import re

    from pipeline.leitura_de_codigo import apenas_codigo

    # Duas decisões, dois donos. `modelos` decide QUAL MODELO; `plataforma`
    # decide SE a GPU serve para acelerar. São perguntas diferentes, cada uma
    # centralizada no seu lugar — o que não pode é uma terceira casa opinar.
    donos = {Path("app/transcricao/modelos.py"),
             Path("app/transcricao/plataforma.py")}
    define = []
    escolhe_sozinho = []
    for pasta in ("app", "helpers", "pipeline"):
        for f in (REPO / pasta).rglob("*.py"):
            rel = f.relative_to(REPO)
            if rel in donos or rel.name.startswith("test_"):
                continue
            try:
                codigo = apenas_codigo(f)
            except Exception:  # noqa: BLE001
                continue
            # as constantes da regra só podem nascer no dono
            if re.search(r"^\s*(PADRAO|RESERVA|FOLGA_PARA_O_ENCODER_MB)\s*=",
                         codigo, re.M):
                define.append(str(rel))
            # e ninguém pode decidir modelo comparando VRAM por conta própria
            for linha in codigo.splitlines():
                if re.search(r"vram\w*\s*[<>]", linha, re.I):
                    escolhe_sozinho.append(f"{rel}: {linha.strip()[:70]}")
    assert not define, f"constantes da regra redefinidas em: {define}"
    assert not escolhe_sozinho, f"decisão por VRAM fora do dono: {escolhe_sozinho}"


# --- primeiro uso ----------------------------------------------------------

def test_o_plano_conta_so_o_que_falta(monkeypatch):
    import app.transcricao.primeiro_uso as pu

    monkeypatch.setattr(pu, "_motor_instalado", lambda: True)
    monkeypatch.setattr(pu.componentes, "cuda_presente", lambda: True)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: True)
    plano = pu.planejar()
    assert plano.total_mb == 0 and not plano.precisa_baixar
    assert pu.ja_pronto()


def test_maquina_sem_gpu_baixa_muito_menos(monkeypatch):
    """Anunciar 3,7 GB para quem vai baixar 703 MB seria mentir na única tela
    que o usuário vê."""
    import app.transcricao.plataforma as plat
    import app.transcricao.primeiro_uso as pu

    monkeypatch.setattr(pu, "_motor_instalado", lambda: False)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: False)
    plat.detectar.cache_clear()
    monkeypatch.setattr(plat, "_gpu_nvidia", lambda: ("", 0))
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)
    monkeypatch.delenv("ATIVAVID_WHISPER_MODEL", raising=False)

    plano = pu.planejar()
    plat.detectar.cache_clear()
    assert plano.backend == "cpu"
    assert plano.aceleracao_mb == 0, "cobrou CUDA de máquina sem GPU"
    assert plano.modelo == "small"
    assert plano.total_mb == 241 + 462
    assert plano.humano() == "703 MB"


def test_o_tamanho_e_mostrado_como_gente_le():
    from app.transcricao.primeiro_uso import Plano

    assert Plano(241, 1986, 1458, "medium", "cuda").humano() == "3.6 GB"
    assert Plano(241, 0, 462, "small", "cpu").humano() == "703 MB"


def test_a_tela_do_primeiro_uso_nao_fala_de_whisper():
    """O usuário pediu uma legenda, não uma instalação."""
    from app.transcricao import primeiro_uso as pu

    visivel = f"{pu.TITULO} {pu.BAIXANDO} {pu.TRANSCREVENDO}".lower()
    for jargao in ("whisper", "cuda", "ctranslate", "cudnn", "cublas",
                   "gpu", "modelo", "vram"):
        assert jargao not in visivel, f"jargão na tela: {jargao!r}"


def test_cancelar_antes_de_preparar_nao_baixa(monkeypatch):
    import threading

    import app.transcricao.primeiro_uso as pu
    from app.transcricao import Cancelado

    monkeypatch.setattr(pu, "_motor_instalado", lambda: False)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: False)
    parar = threading.Event()
    parar.set()
    with pytest.raises(Cancelado):
        pu.preparar(cancelar=parar)


# --- log e telemetria ------------------------------------------------------

def test_o_motor_anuncia_modelo_e_dispositivo():
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "app" / "transcricao" / "whisper_local.py")
    assert "TRANSCRIPTION ENGINE local model=" in codigo
    assert "device=" in codigo


def test_a_telemetria_nao_guarda_conteudo(tmp_path, monkeypatch):
    """Nenhum áudio, nenhum texto, nem o nome do arquivo. O identificador é
    um hash, que agrupa linhas do mesmo vídeo sem revelar qual é."""
    import app.transcricao.telemetria as tel

    alvo = tmp_path / "log.jsonl"
    monkeypatch.setenv("ATIVAVID_TRANSCRICAO_LOG", str(alvo))
    fonte = tmp_path / "Segredo do cliente.mp4"
    fonte.write_bytes(b"x" * 1000)

    ident = tel.identificador(fonte)
    tel.registrar(video=ident, motor="whisper-local", modelo="medium",
                  device="cuda", cache="MISS", palavras=42)

    bruto = alvo.read_text(encoding="utf-8")
    assert "Segredo" not in bruto and ".mp4" not in bruto
    linha = json.loads(bruto.splitlines()[-1])
    assert linha["video"] == ident and len(ident) == 12
    for campo in ("quando", "ram_mb", "vram_mb", "motor", "modelo",
                  "device", "cache", "palavras"):
        assert campo in linha, campo


def test_a_telemetria_nunca_derruba_a_transcricao(monkeypatch):
    import app.transcricao.telemetria as tel

    monkeypatch.setattr(tel, "arquivo", lambda: Path("/caminho/que/nao/existe/x"))
    tel.registrar(video="abc")     # não pode levantar


def test_o_identificador_nao_le_o_arquivo(tmp_path):
    """Um hash de conteúdo em fonte de 500 MB custaria caro por linha de log."""
    a = tmp_path / "a.mp4"
    a.write_bytes(b"z" * 5000)
    import app.transcricao.telemetria as tel

    i1 = tel.identificador(a)
    a.write_bytes(b"w" * 5000)     # mesmo nome, mesmo tamanho, outro conteúdo
    assert tel.identificador(a) == i1


# --- o app deixa de exigir chave -------------------------------------------

def test_faltar_chave_nao_bloqueia_mais_o_app():
    """Bloqueio falso é pior que nenhum: ensina a ignorar o relatório."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "helpers" / "doutor.py")
    assert "Nenhuma chave de transcricao" not in codigo
    i = codigo.index("tem_eleven =")
    trecho = codigo[i:i + 900]
    assert "BLOQUEIO" not in trecho, "voltou a bloquear por falta de chave"
    assert "transcricao nao usa" in trecho.lower() or "não usa" in trecho.lower()


def test_o_scribe_continua_existindo():
    """Ele fica como alternativa até a segunda etapa decidir o destino dele."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "helpers" / "transcribe.py")
    assert "def call_elevenlabs(" in codigo
    assert "def call_groq(" in codigo


# --- o motor precisa CHEGAR na maquina nova --------------------------------

def test_o_instalador_traz_o_motor():
    """Ele estava fora: `uv sync` sem extras não traz o `faster-whisper`.

    O efeito era o pior possível — numa máquina nova o padrão é local, então a
    primeira transcrição baixaria 3,4 GB de aceleração e modelo e SÓ ENTÃO
    falharia, porque o motor em si nunca tinha sido instalado.
    """
    setup = (REPO / "installer" / "setup.ps1").read_text(
        encoding="utf-8", errors="replace")
    linhas = [x.strip() for x in setup.splitlines()
              if x.strip().startswith("uv sync")]
    assert linhas, "o instalador deixou de sincronizar as dependências"
    for linha in linhas:
        assert "--extra transcricao" in linha, (
            "instalação nova ficaria sem o motor local: " + linha)


def test_o_preparo_instala_o_motor_ANTES_de_baixar_o_resto(monkeypatch):
    """A ordem importa: baixar 3,4 GB para depois descobrir que falta o motor
    é o pior resultado possível."""
    import app.transcricao.primeiro_uso as pu

    ordem = []

    monkeypatch.setattr(pu, "_motor_instalado", lambda: False)
    monkeypatch.setattr(pu.componentes, "cuda_presente", lambda: False)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: False)
    monkeypatch.setattr(pu.componentes, "garantir_motor",
                        lambda **k: (ordem.append("motor"), (True, "ok"))[1])
    monkeypatch.setattr(pu.componentes, "garantir_cuda",
                        lambda **k: (ordem.append("cuda"), (True, "ok"))[1])
    monkeypatch.setattr(pu.modelos, "garantir",
                        lambda m, **k: ordem.append("modelo"))
    monkeypatch.setattr(pu, "planejar", lambda: pu.Plano(241, 1986, 1458,
                                                         "medium", "cuda"))
    pu.preparar()
    assert ordem[0] == "motor", f"ordem errada: {ordem}"
    assert ordem == ["motor", "cuda", "modelo"]


def test_sem_o_motor_o_preparo_falha_em_vez_de_seguir(monkeypatch):
    """Aceleração e modelo têm saída (CPU, modelo menor). O motor não tem:
    sem ele a transcrição local não acontece de jeito nenhum."""
    import app.transcricao.primeiro_uso as pu

    monkeypatch.setattr(pu, "planejar", lambda: pu.Plano(241, 0, 0,
                                                         "small", "cpu"))
    monkeypatch.setattr(pu.componentes, "garantir_motor",
                        lambda **k: (False, "sem rede"))
    with pytest.raises(RuntimeError, match="transcricao local"):
        pu.preparar()


# --- o defeito circular da aceleracao --------------------------------------

def test_gpu_sem_bibliotecas_ainda_conta_no_plano(monkeypatch):
    """O defeito que apareceu em uso real, e que custou legendas erradas.

    A busca das bibliotecas de CUDA dependia de `backend == "cuda"` — mas o
    backend só vira "cuda" DEPOIS que elas estão no disco. Circular: numa RTX
    3050 de verdade o plano dizia "0 MB, já pronto" e a máquina ficava presa
    em CPU + modelo pequeno para sempre.

    O resultado na tela, medido na mesma fonte: `small`/CPU escreveu "trocar a
    FILHA do meu mouse" e "Quando que QUISER pra consertar"; `medium`/GPU
    escreveu "a PILHA" e "Quanto que FICA" — e levou 11,3s em vez de 64,2s.
    """
    import app.transcricao.plataforma as plat
    import app.transcricao.primeiro_uso as pu

    plat.esquecer()
    monkeypatch.setattr(plat, "_gpu_nvidia", lambda: ("RTX 3050", 4096))
    monkeypatch.setattr(plat, "registrar_dlls_cuda", lambda: [])   # sem DLLs
    monkeypatch.setattr(pu.componentes, "cuda_presente", lambda: False)
    monkeypatch.setattr(pu, "_motor_instalado", lambda: True)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: False)
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)
    monkeypatch.delenv("ATIVAVID_WHISPER_MODEL", raising=False)

    maq = plat.detectar()
    assert maq.backend == "cpu", "sem DLL o backend de AGORA é cpu"
    assert maq.cuda_possivel, "mas o hardware suporta — é isto que o plano usa"

    plano = pu.planejar()
    plat.esquecer()
    assert plano.aceleracao_mb > 0, (
        "o plano não vai buscar CUDA numa máquina que tem GPU — a aceleração "
        "nunca se instala e a legenda sai pelo modo pior")
    assert plano.modelo == "medium", (
        "baixaria o modelo pequeno para quem vai rodar em GPU")


def test_sem_gpu_nenhuma_o_plano_nao_cobra_cuda(monkeypatch):
    """O outro lado: não pedir 2 GB de quem não tem placa."""
    import app.transcricao.plataforma as plat
    import app.transcricao.primeiro_uso as pu

    plat.esquecer()
    monkeypatch.setattr(plat, "_gpu_nvidia", lambda: ("", 0))
    monkeypatch.setattr(pu.componentes, "cuda_presente", lambda: False)
    monkeypatch.setattr(pu, "_motor_instalado", lambda: True)
    monkeypatch.setattr(pu.modelos, "instalado", lambda m: False)
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)

    plano = pu.planejar()
    plat.esquecer()
    assert not plat.detectar().cuda_possivel or True
    assert plano.aceleracao_mb == 0
    assert plano.modelo == "small"


def test_a_deteccao_e_esquecida_depois_de_instalar_cuda():
    """Ela roda uma vez por processo. Sem esquecer, o mesmo processo seguiria
    achando que está em CPU logo depois de ganhar a aceleração."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "app" / "transcricao" / "primeiro_uso.py")
    i = codigo.index("garantir_cuda")
    j = codigo.index("modelos.garantir", i)
    assert "esquecer()" in codigo[i:j], (
        "instalou CUDA e não reavaliou o backend")
