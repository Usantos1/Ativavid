# -*- coding: utf-8 -*-
"""O card de Concluídos: duração original → final, e início → fim.

Pedido do usuário vendo a tela: "quero a duração original, e duração final;
quero data e hora de início assim como a de conclusão; botão de pasta e legenda
pode ficar dentro do [...] menu".

O card só mostrava "9:16" e a hora de conclusão. Faltavam duas coisas nos
dados, não só no desenho:

- a duração de ORIGEM nunca foi medida (só a entregue, que vem do pipeline);
- `startedAtLabel` era uma cópia de `createdAtLabel`, então "início" dizia a
  hora da IMPORTAÇÃO. Num vídeo que esperou meia hora na fila, os dois números
  não têm nada a ver — e `startedAt`, o de verdade, já era gravado.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _ffmpeg() -> str:
    from app.overlay_compose import _ffmpeg as f

    return f()


@pytest.fixture(scope="module")
def fontes(tmp_path_factory):
    """Dois vídeos REAIS de duração conhecida (2s e 3s).

    Fixture sintética serve aqui: o que se mede é o ffprobe somando durações,
    não o conteúdo. Mas tem de ser arquivo de verdade — um .mp4 falso faria o
    probe devolver 0 e o teste passaria por não medir nada.
    """
    d = tmp_path_factory.mktemp("fontes")
    saidas = []
    for i, seg in enumerate((2, 3), start=1):
        p = d / f"take{i}.mp4"
        subprocess.run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=30:duration={seg}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p),
        ], check=True, capture_output=True)
        saidas.append(p)
    return saidas


def test_a_duracao_de_origem_e_a_soma_das_fontes(fontes):
    from app.local_server import _duracao_das_fontes

    d = _duracao_das_fontes([str(p) for p in fontes])
    assert d == pytest.approx(5.0, abs=0.2), f"esperava ~5s, veio {d}"


def test_fonte_que_nao_existe_nao_derruba_nem_conta(fontes):
    from app.local_server import _duracao_das_fontes

    d = _duracao_das_fontes([str(fontes[0]), str(fontes[0].parent / "sumiu.mp4")])
    assert d == pytest.approx(2.0, abs=0.2)
    assert _duracao_das_fontes([]) == 0.0


def test_o_inicio_e_a_hora_do_processamento_nao_a_da_importacao(tmp_path):
    """O que o usuário pediu como "hora de início". Enquanto era cópia do
    createdAt, um vídeo que esperou na fila mostrava os dois iguais."""
    from app.local_server import enrich_job_display

    job = {
        "createdAt": "2026-08-21T11:21:00Z",
        "startedAt": "2026-08-21T11:52:00Z",
        "finishedAt": "2026-08-21T12:03:00Z",
        "status": "done",
        "editDir": str(tmp_path),
    }
    enrich_job_display(job, tmp_path)
    assert job["createdAtLabel"] != job["startedAtLabel"], (
        "início voltou a ser a hora da importação"
    )
    assert job["startedAtLabel"].endswith("08:52")
    assert job["finishedAtLabel"].endswith("09:03")


def test_sem_startedAt_o_inicio_cai_na_importacao(tmp_path):
    """Job antigo, gravado antes deste campo existir, não pode ficar sem hora."""
    from app.local_server import enrich_job_display

    job = {"createdAt": "2026-08-21T11:21:00Z", "status": "queued",
           "editDir": str(tmp_path)}
    enrich_job_display(job, tmp_path)
    assert job["startedAtLabel"] == job["createdAtLabel"]


def test_a_duracao_ja_medida_atravessa_o_enrich_intacta(tmp_path, fontes):
    """Quem mede e o fundo; o enrich so nao pode estragar o que ja esta la."""
    from app.local_server import enrich_job_display

    job = {
        "createdAt": "2026-08-21T11:21:00Z", "status": "done",
        "editDir": str(tmp_path), "sources": [str(p) for p in fontes],
        "sourceDurationSec": 5.0,
    }
    enrich_job_display(job, tmp_path)
    assert job["sourceDurationSec"] == pytest.approx(5.0, abs=0.01)


def test_a_ficha_do_card_tem_as_seis_linhas():
    """O desenho que o usuário pediu: o NOME manda no card, o selo vem abaixo
    dele, e o resto vira ficha com rótulo — original, editado, formato, estilo,
    início e final."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function fichaHtml(")
    ficha = js[i:i + 1600]
    for rotulo in ("Vídeo original", "Vídeo editado", "Formato", "Estilo",
                   "Início", "Final"):
        assert rotulo in ficha, f"faltou a linha {rotulo!r}"
    assert "sourceDurationSec" in ficha and "styleLabel" in ficha
    k = js.index("function cardSig(")
    assert "j.startedAtLabel" in js[k:k + 1000], (
        "a assinatura do card ignora os campos novos — o card não repinta"
    )
    assert "j.styleLabel" in js[k:k + 1000], "o estilo não entra na assinatura"


def test_o_selo_desce_para_baixo_do_nome_no_card_pronto():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'pc-top${pronto ? " empilhado" : ""}' in js, (
        "o selo continua ao lado do nome no card pronto"
    )
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    assert ".pc-top.empilhado" in css, "falta o estilo do topo empilhado"
    assert ".pc-ficha" in css, "falta o estilo da ficha"


def test_o_card_pronto_nao_repete_video_concluido():
    """A mensagem "Vídeo concluído" não dizia nada que o selo CONCLUÍDO já não
    dissesse, e roubava a ênfase do nome."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function cardHtml(")
    corpo = js[i:js.index("function ", i + 20)]
    assert 'pronto ? "" : (headline ?' in corpo, (
        "o card pronto ainda desenha a mensagem"
    )


def test_pasta_e_legenda_sairam_para_dentro_do_menu():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'title="Abrir a pasta publicar"' not in js, "o botão Pasta continua solto"
    assert 'title="Copiar a legenda do post"' not in js, "o botão Legenda continua solto"
    i = js.index("function cardMenuHtml(")
    menu = js[i:i + 2200]
    for item in ("Abrir pasta", "Copiar legenda do post", "Tentar novamente"):
        assert item in menu, f"faltou {item!r} no menu"


def test_o_menu_do_card_e_refeito_no_patch():
    """Ele era montado uma vez e congelado: "Copiar legenda do post" nunca
    aparecia depois que a legenda ficava pronta, e "Ver vídeo final" ficava
    desabilitado para sempre."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function patchCard(")
    corpo = js[i:i + 6000]
    assert "cardMenuHtml(j, opts)" in corpo, "o patch não refaz o menu"
    assert ".pc-menu:not(.hidden)" in corpo, (
        "o menu seria trocado mesmo aberto, sumindo debaixo do clique"
    )
    assert "fichaHtml(j)" in corpo, "o patch não atualiza a ficha do vídeo"


def test_o_enrich_nunca_mede_dentro_da_requisicao(tmp_path, fontes):
    """A medição da duração de origem NÃO pode acontecer no `enrich_job_display`.

    Ele roda para TODO job em TODO poll da tela. Com os 125 projetos do usuário
    seriam 145 chamadas de ffprobe dentro da requisição — medido, 0,146 s por
    arquivo, **21 segundos** de tela congelada no primeiro poll, e pior com um
    render disputando o disco. Foi assim que a primeira versão disto ficou.
    """
    import time

    from app.local_server import enrich_job_display

    jobs = [
        {"createdAt": "2026-08-21T11:21:00Z", "status": "done",
         "editDir": str(tmp_path), "sources": [str(p) for p in fontes]}
        for _ in range(40)
    ]
    t0 = time.perf_counter()
    for j in jobs:
        enrich_job_display(j, tmp_path)
    dt = time.perf_counter() - t0
    assert dt < 0.5, f"o enrich está medindo dentro da requisição ({dt:.2f}s para 40 jobs)"
    assert all("sourceDurationSec" not in j for j in jobs)


def test_a_medicao_em_fundo_grava_no_store_e_nao_repete(fontes):
    from app.local_server import medir_duracao_em_fundo

    class Store:
        def __init__(self):
            self.escritos = []

        def update(self, jid, **kw):
            self.escritos.append((jid, kw))

    st = Store()
    srcs = [str(p) for p in fontes]
    medir_duracao_em_fundo(st, "job-a", srcs)
    for _ in range(60):
        if st.escritos:
            break
        time.sleep(0.1)
    assert st.escritos, "a medição em fundo nunca gravou"
    jid, kw = st.escritos[0]
    assert jid == "job-a"
    assert kw["sourceDurationSec"] == pytest.approx(5.0, abs=0.2)

    medir_duracao_em_fundo(st, "job-a", srcs)
    time.sleep(0.4)
    assert len(st.escritos) == 1, "o mesmo job foi medido duas vezes"


def test_a_fila_agenda_os_projetos_antigos():
    """Os 125 projetos do usuário não têm o campo — alguém precisa preencher,
    sem segurar a tela."""
    src = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
    assert "medir_duracao_em_fundo" in src, "os projetos antigos nunca ganham a duração"
    i = src.index("medir_duracao_em_fundo(store")
    assert 'sourceDurationSec") in (None, "")' in src[:i], (
        "agenda mesmo quando já foi medido"
    )


def test_copiar_legenda_do_post_tem_handler():
    """O botão existia no card desde sempre e o clique NÃO FAZIA NADA: a cadeia
    de ações tratava folder, open-final, retry, reimport, ackapply, cancel,
    detail e rename — `copylegenda` caía fora dela."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'act === "copylegenda"' in js, "o copiar legenda continua sem handler"
    i = js.index('act === "copylegenda"')
    trecho = js[i:i + 1800]
    assert "copiarTexto(texto)" in trecho
    assert "/api/jobs/${id}/legenda" in trecho, (
        "o copiar usa o retrato do store — texto velho depois de uma correção"
    )
    assert "mostrarTextoParaCopiar" in trecho, (
        "sem saída quando a cópia falha — o usuário queria o texto, não o aviso"
    )


def test_copiar_tem_os_dois_caminhos_e_um_ultimo_recurso():
    """Um caminho só não cobre: a `clipboard` API precisa de contexto seguro E
    da janela em foco, e a janela do app é um WebView."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("async function copiarTexto(")
    corpo = js[i:i + 1200]
    assert "navigator.clipboard.writeText" in corpo
    assert 'document.execCommand("copy")' in corpo, "falta o caminho velho"
    assert "ta.focus()" in corpo, "o execCommand sem foco não copia"
    j = js.index("function mostrarTextoParaCopiar(")
    dlg = js[j:j + 900]
    assert "showModal" in dlg and "selectNodeContents" in dlg, (
        "o último recurso tem de mostrar o texto já selecionado"
    )


def test_o_estilo_do_card_e_o_que_varia():
    """A primeira versão juntava manchete e legenda ("Realce · Empilhado") e o
    usuário reparou na hora: TODOS os cards diziam a mesma coisa. Ele estava
    certo — nos 128 projetos, `headline` e `captions` têm UM valor cada.

    O que varia é o tipo de conteúdo: viral 69, humor 12, informational 12.
    E era isso que ele queria — o exemplo dele foi "Estilo: Viral".
    """
    src = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = src.index("def _ler_rotulo_do_estilo(")
    corpo = src[i:i + 1200]
    assert "contentType" in corpo, "o rótulo voltou a não olhar o tipo"
    assert "preset-used.json" in corpo, "o tipo mora no preset-used"
    assert "from app.content_type import LABELS" in corpo, (
        "catálogo duplicado — as duas telas vão discordar"
    )
    assert "_NOME_HEADLINE" not in src, "o catálogo antigo ficou para trás"


def test_o_rotulo_usa_os_nomes_do_catalogo(tmp_path):
    from app.local_server import _rotulo_do_estilo

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "state.json").write_text("{}", encoding="utf-8")
    (edit / "preset-used.json").write_text(
        json.dumps({"contentType": "viral"}), encoding="utf-8")
    assert _rotulo_do_estilo(edit) == "Viral"

    outro = tmp_path / "outro"
    outro.mkdir()
    (outro / "state.json").write_text("{}", encoding="utf-8")
    (outro / "preset-used.json").write_text(
        json.dumps({"contentType": "informational"}), encoding="utf-8")
    assert _rotulo_do_estilo(outro) == "Informativo"


def test_projeto_sem_tipo_nao_inventa_rotulo(tmp_path):
    """30 dos 128 projetos do usuário são antigos e não têm o campo — a linha
    simplesmente não aparece, em vez de mostrar um valor chutado."""
    from app.local_server import _rotulo_do_estilo

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "state.json").write_text(json.dumps({"style": {}}), encoding="utf-8")
    assert _rotulo_do_estilo(edit) == ""
