# -*- coding: utf-8 -*-
"""O log do render sobrevive ao render.

Tudo que o pipeline conta sobre um vídeo sai em `stdout`, e esse stdout ia
para um arquivo **temporário apagado no fim do job**:

    out_fd, out_name = tempfile.mkstemp(...)
    ...
    p.unlink(missing_ok=True)      # some com tudo

`TIMING_CORTE`, `RENDER_PROPRIO_PULADO`, `UMA_PASSADA_FALLBACK`,
`[legenda] a IA recusou`, os motivos de queda do motor rápido — tudo
escrito para ser lido depois e apagado antes. Só os últimos 800
caracteres do stderr sobreviviam, e só quando o job falhava.

É por isso que tantos defeitos desta base são invisíveis: o comentário que
mais se repete no código é "o pipeline avisava no log, mas o log não
aparece na tela". Ele nem chegava a existir.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import _guardar_log_do_job, _LOG_DO_JOB_MAX  # noqa: E402

LS = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
JV = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_log_fica_ao_lado_do_video(tmp_path):
    _guardar_log_do_job(tmp_path, "TIMING_CORTE juntar=1.2\n", "")
    p = tmp_path / "pipeline.log"
    assert p.is_file() and "TIMING_CORTE" in p.read_text(encoding="utf-8")


def test_chave_e_token_nao_vao_para_o_disco(tmp_path):
    _guardar_log_do_job(tmp_path, "api_key: SEGREDO123\nBearer abc.def\n", "")
    t = (tmp_path / "pipeline.log").read_text(encoding="utf-8")
    assert "SEGREDO123" not in t and "abc.def" not in t


def test_o_stderr_entra_no_fim_com_titulo(tmp_path):
    _guardar_log_do_job(tmp_path, "saida\n", "estourou aqui")
    t = (tmp_path / "pipeline.log").read_text(encoding="utf-8")
    assert "===== stderr =====" in t
    assert t.index("saida") < t.index("estourou aqui")


def test_stderr_vazio_nao_cria_secao(tmp_path):
    _guardar_log_do_job(tmp_path, "saida\n", "   ")
    assert "stderr" not in (tmp_path / "pipeline.log").read_text(encoding="utf-8")


def test_o_teto_guarda_o_FIM(tmp_path):
    """É onde está o erro e o resumo."""
    _guardar_log_do_job(tmp_path, "a" * 100 + "b" * (_LOG_DO_JOB_MAX), "")
    t = (tmp_path / "pipeline.log").read_text(encoding="utf-8")
    assert t.startswith("[..."), "cortou sem avisar"
    assert t.endswith("b")
    assert len(t) < _LOG_DO_JOB_MAX + 200


def test_gravar_o_log_nunca_derruba_o_job():
    """O vídeo é o produto; o log é o extra."""
    _guardar_log_do_job(Path("Z:/nao/existe/mesmo"), "x", "y")


def test_o_worker_grava_antes_de_apagar_o_temporario():
    i = LS.index("_guardar_log_do_job(edit_dir, stdout, stderr)")
    depois = LS[i:i + 400]
    assert "p.unlink(missing_ok=True)" in depois, "apaga antes de guardar"


def test_o_card_so_oferece_o_log_quando_ele_existe():
    """Projeto anterior à 4.11 não tem log — o menu não pode prometer."""
    assert 'j["temLog"] = (edit / "pipeline.log").exists()' in JV
    assert "${j.temLog ?" in JS
    assert 'data-act="log"' in JS
    assert 'if (act === "log")' in JS, "o item existe e não faz nada"


def test_a_rota_existe_e_recusa_o_que_nao_ha():
    i = LS.index('if path == "/api/jobs/open-log":')
    corpo = LS[i:i + 1200]
    assert "pipeline.log" in corpo
    assert '"este vídeo é anterior ao log"' in corpo


# ---------------------------------------------------------------- apply --

AE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")


def test_o_apply_tambem_guarda_o_log(tmp_path):
    """O log do apply só ia para a tela — e o apply roda DENTRO do app,
    cujo stdout no pacote (pythonw) não vai a lugar nenhum. O próprio
    código já dizia o preço: deu para diagnosticar o desperdício do
    RENDER, que grava arquivos, e não o do APPLY, que só imprimia."""
    from app.apply_execute import default_hooks

    h = default_hooks(tmp_path)
    h.log("QUICK_APPLY_REBUILD_SEC 12.3")
    t = (tmp_path / "apply.log").read_text(encoding="utf-8")
    assert "QUICK_APPLY_REBUILD_SEC 12.3" in t


def test_o_log_do_apply_acumula(tmp_path):
    """Um projeto recebe vários applies; o anterior não pode sumir."""
    from app.apply_execute import default_hooks

    h = default_hooks(tmp_path)
    h.log("primeiro")
    h.log("segundo")
    t = (tmp_path / "apply.log").read_text(encoding="utf-8")
    assert "primeiro" in t and "segundo" in t


def test_o_apply_nao_grava_segredo(tmp_path):
    from app.apply_execute import default_hooks

    default_hooks(tmp_path).log("token: SEGREDO123")
    assert "SEGREDO123" not in (tmp_path / "apply.log").read_text(encoding="utf-8")


def test_o_log_do_apply_nunca_derruba_o_apply():
    from app.apply_execute import default_hooks

    default_hooks(Path("Z:/nao/existe")).log("linha qualquer")


def test_o_apply_usa_o_log_de_arquivo():
    i = AE.index("def default_hooks(")
    corpo = AE[i:i + 700]
    assert "log=_log_do_apply(edit_dir)" in corpo, "voltou para o print puro"
