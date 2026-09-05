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
import math
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


def _num(v) -> float:
    """Numero do JSON, tolerante: texto, None ou lixo viram 0.0."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# Etiqueta de clima do arquivo de trilha -> palavra que o usuario reconhece.
_CLIMA_LABEL = {
    "viral": "viral", "humor": "humor", "venda": "venda",
    "anuncio": "anúncio", "resenha": "resenha",
    "informativo": "informativo", "educacional": "educacional",
    "institucional": "institucional", "padrao": "padrão",
    "longform": "vídeo longo",
}


# Backend do plano de corte -> nome que ele reconhece. Os "sem IA" existem
# de propósito (edição leve, corte manual, junção de takes) e dizer isso na
# ficha é a resposta curta para "por que o título não veio da IA".
_IA_LABEL = {
    "gemini-web": "Gemini",
    "chatgpt-web": "ChatGPT",
    "preview_edits": "suas marcações (sem IA)",
    "manual_edl": "seu corte manual (sem IA)",
    "sem_cortes": "sem corte (sem IA)",
    "heuristic_light": "edição leve (sem IA)",
    "multi_take_concat": "junção de takes (sem IA)",
}


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
        # A ficha diz o NOME do que foi usado; o porquê fica no
        # `...Detalhe`, que a tela mostra ao passar o mouse. Pedido dele
        # em 31/08: "não precisa este monte de justificativa, apenas qual
        # IA e trilha usada" — a linha tinha virado um parágrafo.
        job["trilhaNota"] = "Sem trilha"
        job["trilhaDetalhe"] = skip[:200]
    fonte = str(t.get("musicaFonte") or "").strip()
    if fonte and not skip:
        if fonte.startswith("nuvem:"):
            job["trilhaNota"] = "ElevenLabs Music"
        elif fonte.startswith("reuso:"):
            job["trilhaNota"] = "Reaproveitada"
            job["trilhaDetalhe"] = ("a trilha do render anterior servia neste "
                                    "corte — não gastou créditos")
        elif fonte.startswith("motor:"):
            # Dois caminhos levam ao motor local e eles NAO sao a mesma
            # noticia: no modo "IA local" (Configuracoes) ele compoe
            # primeiro, de proposito, e a nuvem nem e chamada. A ficha
            # dizia "o ElevenLabs estava indisponivel" nos dois — e nos
            # dois videos de 30/08 isso era falso, porque o modo dele
            # esta em "local". Sem o motivo gravado (render antigo), o
            # texto fica neutro em vez de acusar.
            motivo = str(t.get("musicaMotivo") or "").strip()
            job["trilhaNota"] = "IA local (MusicGen)"
            if motivo == "escolha":
                job["trilhaDetalhe"] = ("a IA da sua máquina compôs a trilha, "
                                        "sem gastar créditos")
            elif motivo == "reserva":
                # ficha de render antigo (quando a nuvem ainda existia)
                job["trilhaDetalhe"] = "a nuvem não respondeu na época"
        else:
            # O NOME DO ARQUIVO nao serve de recado: "anuncio--20260822-
            # 193504_a001_08221324_cf96c4.mp3" nao diz nada ao usuario, nao
            # quebra linha e estourava a largura do card. O que importa e o
            # clima da faixa, que e o prefixo antes do "--".
            clima = _CLIMA_LABEL.get(fonte.split("--", 1)[0].lower(), "")
            # POR QUE veio da biblioteca importa: "a IA falhou" mandava
            # procurar defeito onde so havia fila (outro video compondo).
            motivo = str(t.get("musicaMotorRecusa") or "").strip()
            job["trilhaNota"] = f"Sua biblioteca{f' ({clima})' if clima else ''}"
            job["trilhaDetalhe"] = (
                motivo or "a IA de música não compôs nesta geração")
    ec = str(t.get("endCardSkip") or "").strip()
    if ec:
        job["cardFinalNota"] = f"Card final desligado: {ec[:110]}"
    perdida = t.get("midiaDoEditorPerdida") or []
    if isinstance(perdida, list) and perdida:
        # O usuario POS na mao e nao veio: sem esta linha ele procura o
        # proprio erro num arquivo que o render nao achou.
        job["midiaNota"] = (
            f"{len(perdida)} mídia(s) que você inseriu não estavam na pasta do "
            f"projeto e ficaram de fora: {', '.join(str(x)[:28] for x in perdida[:3])}")
    # Video entregue com legenda cobrindo so parte da fala (caso real de
    # 31/08: 12s legendados num video de 24s) — o aviso vinha num [warn]
    # que nao e guardado; agora o render grava e o card mostra.
    cob = str(t.get("legendaCobertura") or "").strip()
    ia = str(t.get("legendaIA") or "").strip()
    if cob:
        job["legendaNota"] = cob
    elif ia:
        job["legendaNota"] = ia
    ft = t.get("fonteSemAcento") or {}
    if isinstance(ft, dict) and ft.get("faltam"):
        # Desde 01/09 os dois motores cobrem o glifo que falta com a fonte
        # padrao (como o Chrome faz) — o video nao sai mais com o carimbo
        # da DEMO, mas essas letras ficam NUMA FONTE DIFERENTE do resto.
        job["fonteNota"] = (
            f"A fonte {str(ft.get('arquivo') or '')[:40]} não tem "
            f"{str(ft.get('faltam'))[:14]} — essas letras saem na fonte "
            "padrão. Para tudo na sua fonte, use a versão completa dela.")
    fora = t.get("trechosForaDaFonte") or []
    if isinstance(fora, list) and fora:
        # Sem esta nota o defeito e MUDO: o video sai pronto, com pedaco
        # sem som e travado, e a culpa parece ser da gravacao.
        fontes = sorted({str(f.get("fonte") or "?") for f in fora
                         if isinstance(f, dict)})
        quantos = len(fora)
        job["corteNota"] = (
            f"{quantos} trecho{'s' if quantos > 1 else ''} pedia"
            f"{'m' if quantos > 1 else ''} tempo que o arquivo não tem "
            f"({', '.join(fontes)[:60]}) — foram tirados do corte")


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


def _qualidade_do_corte(job: dict, edit: Path) -> None:
    """"Sobrou 1,4s de pausa" na ficha do card.

    O pipeline sempre mediu isso (verify_cut) e sempre jogou fora. Nos 10
    videos mais recentes do usuario (27/08): 6 tinham pausa sobrando e 6
    tinham um trecho mais baixo que o resto — defeitos pequenos, mas que
    ele so descobriria assistindo. O aviso so aparece quando incomoda:
    pausa somando 0,8s ou queda de 6 dB.
    """
    try:
        d = json.loads((edit / "verificacao.json").read_text(
            encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    # Nos modos que PRESERVAM a fonte (Sem cortes, Vídeo completo, Edição
    # leve) a pausa NAO e defeito: e o que o usuario pediu. O primeiro
    # video real a receber este aviso (27/08, modo "Sem cortes") ganhou
    # "6 pausas somando 4,9s" — mandando arrumar o que o proprio modo
    # manda manter. Mesma armadilha do aviso de IA que mandava recapturar
    # sessao viva: o conselho tem de seguir a CAUSA.
    try:
        modo = str(json.loads(
            (edit / "job_intent.json").read_text(encoding="utf-8-sig")
        ).get("editingIntent") or "").lower()
    except (OSError, json.JSONDecodeError):
        modo = ""
    # SO "Sem cortes" (intact) preserva as pausas: e o modo que nao passa
    # tesoura nenhuma. "Edicao leve" corta exatamente silencio e erro, e
    # "Video completo" tambem tira silencio e repeticao (ver os comentarios
    # de app/editing_intent.py) — neles, pausa sobrando E defeito do corte,
    # que e justamente o que este aviso existe para contar. A 3.17 calou os
    # tres de uma vez porque o caso real que a motivou era intact.
    preserva = modo == "intact"
    partes = []
    total = _num(d.get("silencioTotalS"))
    if not math.isfinite(total):
        total = 0.0
    quantas = len(d.get("silenciosSobrando") or [])
    if quantas and total >= 0.8 and not preserva:
        onde = (d.get("silenciosSobrando") or [{}])[0].get("inicio")
        tempo = f"{total:.1f}".replace(".", ",")
        quando = (f" (a 1ª aos {int(onde // 60)}:{int(onde % 60):02d})"
                  if onde is not None else "")
        partes.append(
            (f"{quantas} pausas somando {tempo}s" if quantas > 1
             else f"1 pausa de {tempo}s") + quando)
    # Projeto gravado por uma versao anterior pode ter -Infinity aqui (JSON
    # aceita, Python le, e o int() explode) — um unico projeto assim deixava
    # a Fila INTEIRA em branco, porque o /api/jobs morre inteiro.
    # Precisa ser numero FINITO e negativo: "quedaDb": null virava
    # `0.0` e o card dizia "voz 0 dB mais baixa" — aviso sem sentido.
    baixos = [x for x in (d.get("takesBaixos") or [])
              if math.isfinite(_num(x.get("quedaDb")))
              and _num(x.get("quedaDb")) < 0]
    if baixos:
        pior = abs(min(_num(x.get("quedaDb")) for x in baixos))
        # meio-a-meio arredonda PARA CIMA: 8,5 dB virava "8 dB" com o
        # arredondamento bancário do Python, e quem lê espera 9.
        db = int(pior + 0.5)
        partes.append(
            (f"{len(baixos)} trechos com a voz até {db} dB mais baixa"
             if len(baixos) > 1
             else f"1 trecho com a voz {db} dB mais baixa"))
    estouros = int(d.get("emendasEstouradas") or 0)
    if estouros:
        partes.append(f"{estouros} emenda com estouro" if estouros == 1
                      else f"{estouros} emendas com estouro")
    if partes:
        job["corteQualidade"] = " · ".join(partes)


def _pedido_nao_aplicado(job: dict, edit: Path) -> None:
    """Correção salva no editor que nunca virou vídeo.

    O painel de projetos já conta isso; a Fila e os Concluídos, não —
    e é neles que ele olha. Medido nos projetos do usuário: **12 têm um
    pedido salvo e nunca aplicado**, o mais antigo de 13/08. Trabalho que
    ele fez e que não chegou ao vídeo, sem nada na tela dizendo.

    Só conta o que é MAIS NOVO que o vídeo entregue: arquivo de pedido
    mais velho que a entrega já foi aplicado, e o arquivo é sobra.
    """
    alvos = [(edit / "preview_edits.json", "marcações no editor"),
             (edit / "preview_style.json", "troca de estilo"),
             # 5.0.38: as correções RÁPIDAS (texto de legenda, manchete,
             # trecho) moram em `corrections.json` e nunca entravam aqui.
             # Medido em 05/09: **7 projetos** com correção salva e nunca
             # aplicada, o mais velho de 18/08 — nenhum aparecia.
             (edit / "corrections.json", "correções rápidas")]
    try:
        from app.local_server import resolve_delivery_mp4

        final = resolve_delivery_mp4(edit)
        t_final = final.stat().st_mtime if final else 0.0
    except Exception:  # noqa: BLE001
        t_final = 0.0
    for caminho, oque in alvos:
        try:
            if not caminho.is_file():
                continue
            if t_final and caminho.stat().st_mtime <= t_final:
                continue
            if caminho.name == "corrections.json" and not _correcao_suja(caminho):
                continue
        except OSError:
            continue
        job["pedidoNota"] = (f"há {oque} salvas neste projeto que ainda não "
                             f"foram aplicadas ao vídeo")
        # 5.0.46: o card sabe O QUE esta pendente — correcao rapida tem
        # botao de aplicar ali mesmo; marcacao/estilo abre o editor.
        job["pedidoTipo"] = ("correcoes" if caminho.name == "corrections.json"
                             else "estilo" if caminho.name == "preview_style.json"
                             else "marcacoes")
        return


def _correcao_suja(caminho: Path) -> bool:
    """`corrections.json` com algo por aplicar.

    O arquivo existe em quase todo projeto (o render o reescreve para
    rebatizar o relógio — `_clear_dirty`), então existir não diz nada; o
    que diz é o `dirty` com alguma chave ligada ou o `finalStale`.
    """
    try:
        d = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(d, dict):
        return False
    sujo = d.get("dirty")
    if isinstance(sujo, dict) and any(sujo.values()):
        return True
    return bool(d.get("finalStale"))


# O que o caminho RAPIDO sabe desenhar (`overlayReasons` do
# `app/render_path.py`). Um FULL cujos motivos cabem todos aqui nao foi
# escolha do classificador: foi o motor rapido estar desligado.
_RAZOES_DO_RAPIDO = frozenset({
    "captions", "hook", "end_card", "inserts", "flash", "logo",
})


# O motor proprio comecou a desenhar em 21/08/2026 (primeiro
# `overlayEngine: proprio` nos projetos). Antes disso, um video no caminho
# completo nao tinha alternativa — avisar sobre o que ninguem podia mudar e
# a licao que este arquivo ja carrega. Depois, FULL sem falha significa que
# o desenho rapido estava DESLIGADO, e ai e noticia.
_MOTOR_PROPRIO_DESDE = "20260821"


def _depois_do_motor_proprio(edit: Path) -> bool:
    nome = edit.parent.name[:8]
    return nome.isdigit() and nome >= _MOTOR_PROPRIO_DESDE


def _aviso_do_motor(job: dict, edit: Path) -> None:
    """Diz quando o vídeo saiu pelo caminho LENTO — e por quê.

    O motor próprio desenha sem abrir o Chrome e é 3,3x mais rápido (423s
    contra 1391s de média nos 404 jobs do usuário). Quando ele fica de
    fora, o vídeo demora o triplo e nada na tela contava: o motivo ia para
    o `timing.json` e morria lá.

    Aparece pouco de propósito — 79% dos vídeos usam o motor rápido. Aviso
    raro é aviso que se lê.
    """
    try:
        d = json.loads((edit / "timing.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(d, dict):
        return
    motivo = str(d.get("overlayEngineSkip") or "").strip()
    if motivo:
        job["motorNota"] = f"desenho pelo caminho lento — {motivo}"[:160]
        return
    razoes = {str(x) for x in (d.get("renderPathReasons") or [])}
    # O caminho completo por FALHA do rápido — isto é notícia. O caminho
    # completo puro NÃO entra: 33 dos projetos do usuário são de antes do
    # motor próprio existir, e avisar sobre o que ele não pode mudar
    # ensina a ignorar aviso (a lição que este arquivo já carrega).
    if {"OVERLAY_FAILED", "FALLBACK_FULL_REMOTION"} & razoes:
        job["motorNota"] = ("o desenho rápido falhou e o vídeo foi refeito "
                            "pelo caminho completo, cerca de 3x mais lento")
        return
    # Caminho completo SEM falha e com motivos que o rapido atende: o
    # caminho rapido estava DESLIGADO na maquina. Acontece quando uma
    # pausa do canary grava `overlayRollout=off` — e ai vale para todos os
    # videos seguintes, nao so para este. Quatro videos dele sao assim
    # (25/08 x3, 29/08 x1). Isto e noticia; o "caminho completo puro" de
    # antes do motor proprio existir continua fora.
    if (str(d.get("renderPath") or "") == "FULL" and not d.get("fallbackUsed")
            and razoes and razoes <= _RAZOES_DO_RAPIDO
            and _depois_do_motor_proprio(edit)):
        job["motorNota"] = ("saiu pelo caminho completo, cerca de 3x mais "
                            "lento — o desenho rápido estava desligado")
        return
    # Motor próprio de fora SEM motivo registrado: acontece em projeto
    # anterior à versão que passou a gravar o porquê. Dizer que foi lento
    # continua sendo verdade — inventar o motivo é que não.
    if str(d.get("overlayEngine") or "") == "remotion":
        job["motorNota"] = ("desenho pelo caminho lento (motivo não "
                            "registrado nesta versão)")


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
        backend = str(llm.get("backend") or "")
        if backend == "groq":
            # O conselho segue o MOTIVO: "recapture" só vale quando as
            # sessões caíram; resposta ilegível com sessão viva não tem o
            # que recapturar (caso real 26/08 — a nota mandou recapturar
            # com o Gemini saudável e confundiu o usuário).
            job["iaNota"] = "Groq (plano B)"
            if str(llm.get("groqVia") or "") == "parse":
                job["iaDetalhe"] = ("a IA principal respondeu ilegível nesta "
                                    "geração. O vídeo saiu com IA normalmente.")
            else:
                job["iaDetalhe"] = ("as sessões web caíram. Recapture em "
                                    "Chaves & IA.")
        elif backend in _IA_LABEL:
            # A ficha respondia "qual IA?" só quando algo dava errado. Ele
            # pediu a linha em todo vídeo (31/08) — é o nome, uma palavra,
            # não uma justificativa.
            job["iaNota"] = _IA_LABEL[backend]
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


# O rotulo de formato do card. A tela chumbar "9:16" mentia para todo
# preset que nao fosse Reels — caso real de 02/09: video de YouTube (fonte
# 1920x1080, exportPreset=youtube) na Fila com "9:16" ao lado da duracao.
_FORMATO_LABEL = {"reels": "9:16", "youtube": "16:9",
                  "square": "1:1", "feed": "4:5"}


def _formato_do_video(job: dict, edit: Path) -> None:
    """`formatLabel` a partir do preset USADO no job (preset-used.json);
    sem ele (job na fila, projeto velho), do preset pedido no proprio job."""
    preset = None
    try:
        preset = json.loads((edit / "preset-used.json")
                            .read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        pass
    if not isinstance(preset, dict):
        preset = job.get("preset") if isinstance(job.get("preset"), dict) else {}
    exp = str((preset or {}).get("exportPreset") or "").strip().lower()
    rotulo = _FORMATO_LABEL.get(exp)
    if rotulo:
        job["formatLabel"] = rotulo


def job_do_projeto(store: Any, edit_dir: Path) -> dict | None:
    """O registro do job cujo editDir é `edit_dir` (comparação sem ligar
    para barra ou caixa), ou None quando o projeto não é um job."""
    alvo = str(edit_dir).replace("\\", "/").rstrip("/").lower()
    for j in store.list():
        ed = str(j.get("editDir") or "").replace("\\", "/").rstrip("/").lower()
        if ed and ed == alvo:
            return j
    return None


def titulo_do_card(store: Any, edit_dir: Path) -> str | None:
    """O nome que o CARD do hub mostra para o projeto de `edit_dir`.

    Espelho do `displayTitle` da tela (03/09: o editor mostrava "Bateria
    descarregando rápido..." e o card "G2 · C1 · CTA2" — regras diferentes):
    título travado > stem do arquivo final (exceto final/cut genéricos) >
    título resolvido do job. None quando o projeto não é um job.
    """
    job = job_do_projeto(store, edit_dir)
    if not job:
        return None
    if job.get("titleLocked") and str(job.get("title") or "").strip():
        return str(job["title"]).strip()[:80]
    if str(job.get("status") or "") == "done" and job.get("final"):
        stem = Path(str(job["final"])).stem.strip()
        if stem and stem.lower() not in ("final", "cut"):
            return stem[:80]
    try:
        from app.local_server import _resolve_job_title
        return str(_resolve_job_title(job, edit_dir) or "")[:80] or None
    except Exception:  # noqa: BLE001
        return str(job.get("title") or job.get("name") or "")[:80] or None


def ficha_do_card(store: Any, edit_dir: Path) -> dict | None:
    """{id, title} do card — o editor precisa do id para renomear/aprovar
    (03/09: "poder renomear o G1·C3·CTA2 quando eu quiser" + checkbox
    Aprovado que poe o ✅ na frente do nome)."""
    job = job_do_projeto(store, edit_dir)
    if not job or not job.get("id"):
        return None
    return {"id": str(job["id"]), "title": titulo_do_card(store, edit_dir) or ""}


# Cache do card PRONTO. A montagem lê ~13 arquivos por projeto (timing,
# verificação, corte, preset, ficha...) e com 246 projetos eram 3.200
# leituras por chamada — 1 a 2 s a cada volta do preview (02/09). Job
# concluído não muda sozinho: a assinatura é o próprio registro do banco +
# o mtime da pasta edit e do timing.json (um "Aplicar" reescreve os dois).
_CACHE_PRONTOS: dict[str, tuple[str, dict]] = {}


def _assinatura_do_pronto(j: dict, edit: Path, com_links: bool) -> str:
    import os

    def _mt(p: Path) -> int:
        try:
            return os.stat(p).st_mtime_ns
        except OSError:
            return 0

    return (f"{json.dumps(j, sort_keys=True, default=str)}|{int(com_links)}"
            f"|{_mt(edit)}|{_mt(edit / 'timing.json')}")


def _aliviar_card(j: dict) -> None:
    """Tira do card o que a tela não usa — a lista vai inteira a cada 2,5 s.

    Medido em 05/09 no app dele (331 projetos, 877 KB por pedido): a
    legenda do post era 18% e o `score.json` inteiro 10%. A tela usa a
    legenda só como "tem/não tem" (o botão Copiar busca o arquivo FRESCO
    em `/api/jobs/<id>/legenda`, porque o retrato envelhece) e do score só
    `overall` e a primeira dica.
    """
    if j.get("legenda"):
        j["temLegenda"] = True
        j["legenda"] = ""
    sc = j.get("score")
    if isinstance(sc, dict):
        dicas = sc.get("tips") if isinstance(sc.get("tips"), list) else []
        j["score"] = {"overall": sc.get("overall"), "tips": [d for d in dicas if d][:1]}


def build(store: Any, projects_root: Path, *, com_links: bool = False) -> list[dict]:
    """Cards prontos para a tela, do mais recente para o mais antigo."""
    import copy

    from app.local_server import (  # import tardio: o local_server usa este módulo
        STAGE_LABELS,
        enrich_job_display,
        medir_duracao_em_fundo,
        resolve_delivery_mp4,
    )

    jobs = store.list()
    for idx, j in enumerate(jobs):
        edit = Path(j.get("editDir") or "")
        assinatura = None
        if str(j.get("status") or "") == "done" and j.get("id"):
            assinatura = _assinatura_do_pronto(j, edit, com_links)
            guardado = _CACHE_PRONTOS.get(str(j["id"]))
            if guardado and guardado[0] == assinatura:
                jobs[idx] = copy.deepcopy(guardado[1])
                continue
        _montar_card(j, edit, com_links, STAGE_LABELS, enrich_job_display,
                     medir_duracao_em_fundo, resolve_delivery_mp4, store)
        if assinatura is not None:
            _CACHE_PRONTOS[str(j["id"])] = (assinatura, copy.deepcopy(j))
    _CACHE_PRONTOS_LIMPAR({str(j.get("id")) for j in jobs})

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


def _CACHE_PRONTOS_LIMPAR(vivos: set[str]) -> None:
    """Job apagado sai do cache — senão o dicionário só cresce."""
    for k in [k for k in _CACHE_PRONTOS if k not in vivos]:
        _CACHE_PRONTOS.pop(k, None)


def _marca_do_projeto(j: dict, edit: Path) -> str:
    """De qual EMPRESA (marca) e este video — workspace por empresa (5.0.0).

    O job nao guardava isso; quem sabe e o projeto: `preset-used.json`
    (gravado no render) e, antes do render, `job_intent.json` (gravado na
    importacao). Vazio = "sem empresa" (aparece em todos os workspaces).
    """
    bid = str(j.get("brandId") or "").strip()
    if bid:
        return bid
    for nome in ("preset-used.json", "job_intent.json"):
        try:
            d = json.loads((edit / nome).read_text(encoding="utf-8-sig"))
            bid = str((d or {}).get("brandId") or "").strip()
            if bid:
                return bid
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return ""


def _montar_card(j: dict, edit: Path, com_links: bool, STAGE_LABELS, enrich_job_display,
                 medir_duracao_em_fundo, resolve_delivery_mp4, store) -> None:
    """O card de UM job (a parte cara: leituras de arquivo)."""
    if True:
        j["brandId"] = _marca_do_projeto(j, edit)
        j["hasCut"] = (edit / "cut.mp4").exists()
        j["hasFinal"] = resolve_delivery_mp4(edit) is not None
        j["hasThumb"] = (edit / "thumb.jpg").exists()
        # O log do render (`pipeline.log`) so passou a existir na 4.11.
        # Projeto antigo nao tem, e o menu nao pode oferecer o que nao ha.
        j["temLog"] = (edit / "pipeline.log").exists()
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
        _aliviar_card(j)
        _formato_do_video(j, edit)
        _fonte_do_video(j, edit)
        _modo_de_edicao(j, edit)
        _resumo_do_corte(j, edit)
        _qualidade_do_corte(j, edit)
        _aviso_de_trilha(j, edit)
        _estado_de_publicacao(j, edit)
        _aviso_de_ia(j, edit)
        _aviso_do_motor(j, edit)
        _pedido_nao_aplicado(j, edit)
        enrich_job_display(j, edit)
        if j.get("sourceDurationSec") in (None, "") and (j.get("sources") or j.get("source")):
            # Projeto de antes deste campo existir. A medicao vai para o fundo
            # e o proximo poll ja acha pronta — a requisicao nunca espera.
            medir_duracao_em_fundo(store, str(j.get("id") or ""),
                                   j.get("sources") or [j.get("source")])

