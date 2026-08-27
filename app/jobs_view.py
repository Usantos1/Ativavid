"""Monta a lista de cards da Fila — uma implementação só.

O /api/jobs existia duas vezes, quase igual, no local_server e no
desktop_server. Foi exatamente por isso que o defeito dos campos de visão
grudando no card precisou ser caçado em dois lugares. Aqui a vista é montada
num lugar só; a diferença real entre os dois (a desktop também dá os links do
editor) é um parâmetro.

Tudo o que este módulo escreve são campos DERIVADOS: valem para esta resposta
e não voltam para a fila — o store entrega cópias justamente para isso.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _status_do_pipeline(job: dict, edit: Path) -> None:
    """Passo e progresso vêm do pipeline_status.json, que é escrito pelo run."""
    st_path = edit / "pipeline_status.json"
    if job.get("status") == "processing" and st_path.exists():
        try:
            st = json.loads(st_path.read_text(encoding="utf-8-sig"))
            job["stage"] = st.get("stage") or "processing"
            job["progress"] = st.get("progress")
            if st.get("message"):
                job["message"] = st["message"]
        except (OSError, json.JSONDecodeError):
            job["stage"] = "processing"
    else:
        job["stage"] = job.get("status")


# Backends que NAO sao falha: o corte veio do editor do proprio usuario, do
# modo leve (que dispensa IA de proposito) ou da juncao de varios takes.
# `ok: False` no result.json e so o caso ruim mesmo — a IA foi chamada e nao
# respondeu.
# Rotulos dos modos que MUDAM como o corte e feito. "dynamic" e o padrao e
# fica implicito; os outros aparecem na ficha do card — sem isso o usuario
# nao tem como ver que um video saiu da Edicao leve, e foi exatamente o que
# escondeu a causa de "todo modo fica com a mesma minutagem" (24/08): tres
# imports do mesmo video herdaram o modo leve em silencio e o corte
# heuristico saiu identico tres vezes.
_MODO_LABEL = {
    "intact": "Sem cortes",
    "light": "Edição leve",
    "complete": "Vídeo completo",
    "shorts": "Reels / Shorts",
}


def _fonte_do_video(job: dict, edit: Path) -> None:
    """Stem do ARQUIVO de origem — a chave que agrupa as versoes do mesmo
    video ("Gerar 5 versoes" cria 5 projetos da mesma fonte; o Comparar
    precisa saber quem e irmao de quem)."""
    try:
        st = json.loads((edit / "state.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    proj = str(st.get("project") or "").strip()
    if proj:
        job["fonteStem"] = Path(proj).stem


def _estado_de_publicacao(job: dict, edit: Path) -> None:
    """Instagram no card: publicado (com link), publicando, ou falha."""
    try:
        d = json.loads((edit / "publicacao.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    estado = str(d.get("estado") or "")
    if estado == "ok":
        job["publicadoLink"] = str(d.get("permalink") or "")
        job["publicadoEm"] = str(d.get("at") or "")
    elif estado == "rodando":
        job["publicando"] = True
    elif estado == "erro":
        job["publicacaoErro"] = str(d.get("error") or "")[:120]


def _aviso_de_trilha(job: dict, edit: Path) -> None:
    """"Sem trilha" no card. Video pedia musica de IA, a geracao falhou e ate
    25/08 nada avisava (caso real: creditos do ElevenLabs esgotados — o
    video saiu mudo de musica e so uma auditoria manual descobriu)."""
    try:
        t = json.loads((edit / "timing.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    skip = str(t.get("musicaSkip") or "").strip()
    if skip:
        job["trilhaNota"] = f"Sem trilha sonora: {skip[:110]}"
    fonte = str(t.get("musicaFonte") or "").strip()
    if fonte and not skip:
        job["trilhaNota"] = (f"Trilha da sua biblioteca: {fonte[:70]} "
                             "(a IA de música falhou nesta geração)")
    ec = str(t.get("endCardSkip") or "").strip()
    if ec:
        job["cardFinalNota"] = f"Card final desligado: {ec[:110]}"


def _resumo_do_corte(job: dict, edit: Path) -> None:
    """"Saiu: 32s silêncio · 9s repetição" na ficha do card. A auditoria do
    corte era feita na mão abrindo EDL + transcrição (24-25/08); agora o
    pipeline grava corte_relatorio.json e o card conta o que saiu."""
    try:
        d = json.loads((edit / "corte_relatorio.json").read_text(
            encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    if d.get("removedSec") is None:
        return
    if float(d.get("removedSec") or 0) < 0.5:
        job["corteResumo"] = "nada — vídeo inteiro"
    elif d.get("resumo"):
        job["corteResumo"] = str(d["resumo"])[:90]


def _modo_de_edicao(job: dict, edit: Path) -> None:
    try:
        d = json.loads((edit / "job_intent.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    rot = _MODO_LABEL.get(str(d.get("editingIntent") or ""))
    if rot:
        job["modoLabel"] = rot


def _aviso_de_ia(job: dict, edit: Path) -> None:
    """Marca o card quando o vídeo saiu sem o planejamento por IA.

    Existe por causa de um prejuízo real: a extensão parou de entregar a sessão
    e o planejamento caiu para o corte heurístico, que tira a headline das
    primeiras palavras da fala. O pipeline avisava — em `[ia] fallback
    heurístico` no log — mas o log não aparece na tela. Em 20 e 21/08 saíram
    50 vídeos assim e nada na Fila dizia o que tinha mudado.
    """
    if job.get("status") != "done":
        return
    try:
        r = json.loads((edit / "result.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    llm = r.get("llm")
    if not isinstance(llm, dict):
        return
    if llm.get("ok"):
        # Sucesso pelo PLANO B: o video saiu certo, mas as sessoes web
        # cairam e o plano veio do Groq. Em 24/08 isso aconteceu as 23h e o
        # usuario so saberia abrindo o painel de IA — o card agora conta na
        # hora, como nota (nao e erro).
        if str(llm.get("backend") or "") == "groq":
            # O conselho segue o MOTIVO: "recapture" só vale quando as
            # sessões caíram; resposta ilegível com sessão viva não tem o
            # que recapturar (caso real 26/08 — a nota mandou recapturar
            # com o Gemini saudável e confundiu o usuário).
            if str(llm.get("groqVia") or "") == "parse":
                job["iaNota"] = ("Plano B (Groq): a IA principal respondeu "
                                 "ilegível nesta geração. O vídeo saiu com "
                                 "IA normalmente.")
            else:
                job["iaNota"] = ("Plano B (Groq): as sessões web caíram. "
                                 "Recapture em Chaves & IA.")
        return
    # O CONSELHO tem de seguir a causa. A primeira versao mandava "reconecte
    # em Chaves & IA" em todo caso — e nos projetos reais 65 dos 67 avisos
    # seriam por `KeyError: 'viral'`, um defeito de código já corrigido: a
    # sessão estava boa e reconectar não resolveria nada. Mandar o usuário
    # mexer na conexão para consertar um defeito meu é pior que não avisar.
    motivo = str(llm.get("error") or "").lower()
    de_sessao = any(x in motivo for x in ("sess", "captur", "extens", "login"))
    job["iaAviso"] = (
        "Saiu sem IA: o título veio das primeiras palavras da fala. "
        + ("Reconecte em Chaves & IA e gere de novo."
           if de_sessao else "Gere de novo para o título sair da IA."))


def build(store: Any, projects_root: Path, *, com_links: bool = False) -> list[dict]:
    """Cards prontos para a tela, do mais recente para o mais antigo."""
    from app.local_server import (  # import tardio: o local_server usa este módulo
        STAGE_LABELS,
        enrich_job_display,
        medir_duracao_em_fundo,
        resolve_delivery_mp4,
    )

    jobs = store.list()
    for j in jobs:
        edit = Path(j.get("editDir") or "")
        j["hasCut"] = (edit / "cut.mp4").exists()
        j["hasFinal"] = resolve_delivery_mp4(edit) is not None
        j["hasThumb"] = (edit / "thumb.jpg").exists()
        j["thumbUrl"] = f"/api/jobs/{j['id']}/thumb"
        if com_links:
            enc = quote(Path(j.get("projectDir") or "").name, safe="-_.")
            j["editorUrl"] = f"/p/{enc}/fase1"
            j["estiloUrl"] = f"/p/{enc}/estilo"
            j["finalUrl"] = f"/p/{enc}/fase2"
        _status_do_pipeline(j, edit)
        j["stageLabel"] = STAGE_LABELS.get(str(j.get("stage") or ""), j.get("message") or "")
        score_path = edit / "score.json"
        if score_path.exists():
            try:
                j["score"] = json.loads(score_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                pass
        _fonte_do_video(j, edit)
        _modo_de_edicao(j, edit)
        _resumo_do_corte(j, edit)
        _aviso_de_trilha(j, edit)
        _estado_de_publicacao(j, edit)
        _aviso_de_ia(j, edit)
        enrich_job_display(j, edit)
        if j.get("sourceDurationSec") in (None, "") and (j.get("sources") or j.get("source")):
            # Projeto de antes deste campo existir. A medicao vai para o fundo
            # e o proximo poll ja acha pronta — a requisicao nunca espera.
            medir_duracao_em_fundo(store, str(j.get("id") or ""),
                                   j.get("sources") or [j.get("source")])

    try:
        from app.eta_estimate import attach_eta, collect_history

        hist = collect_history(projects_root)
        for j in jobs:
            attach_eta(j, hist, Path(j.get("editDir") or ""))
    except Exception:  # noqa: BLE001 - a estimativa nunca pode derrubar a Fila
        pass

    try:
        from app.apply_tasks import enrich_jobs_list

        enrich_jobs_list(jobs, projects_root)
    except Exception:  # noqa: BLE001
        pass
    return jobs
