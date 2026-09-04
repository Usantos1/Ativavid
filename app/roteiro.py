# -*- coding: utf-8 -*-
"""Roteiro de gravação: um chat com a IA que conhece a empresa.

Pedido de 03/09: "um criador de roteiro de gravação, tipo uma conversa com
a IA, abaixo de Presets, com botões prontos pra pessoa preencher a ideia; a
gente manda pra LLM todos os dados da empresa e regras no prompt de como
ela deve devolver o roteiro limpo pra gravar; salvar a memória dos chats
local; copiar as respostas; escolher o estilo do vídeo; ganchos fortes que
param o scroll".

Desenho:
- a IA e a mesma do corte (`llm_gateway.chat_com_rede`: sessao do
  navegador, Groq de plano B) — sem chave nova, sem token;
- os dados da empresa vivem na MARCA (`brands/<id>.json`, campo `empresa`),
  entao cada marca tem o seu roteirista;
- cada conversa e um arquivo em `%USERPROFILE%/ATIVAVID/roteiros/<marca>/`,
  com titulo, opcoes e as mensagens — memoria local, sem servidor;
- a resposta segue um formato FIXO e sem enfeite (sem markdown, sem emoji):
  ganchos, roteiro por blocos com tempo, CTA, texto na tela, legenda do
  post. E o que da para copiar e ler no teleprompter.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.brand_kits import BRANDS_DIR, USER_DIR, _slug, ensure_brands_dir, load_brand

ROTEIROS_DIR = USER_DIR / "roteiros"
MAX_HISTORICO = 12          # mensagens anteriores que voltam para a IA
MAX_CHARS_MSG = 6000

ESTILOS: list[dict[str, str]] = [
    {"id": "venda", "nome": "Venda direta",
     "regra": "Abre com a dor ou o desejo do cliente, mostra a solução em 1-2 frases concretas e fecha com uma oferta clara. Zero enrolação."},
    {"id": "viral", "nome": "Viral / curiosidade",
     "regra": "Gancho que gera curiosidade ou choque nos 2 primeiros segundos, ritmo rápido, uma virada no meio e fecho que pede comentário ou compartilhamento."},
    {"id": "educativo", "nome": "Educativo (dica)",
     "regra": "Promete um aprendizado específico no gancho, entrega em passos curtos e numerados, sem jargão, e fecha convidando a salvar."},
    {"id": "erro", "nome": "Erro comum / mito",
     "regra": "Começa com o erro ou mito que o público comete, mostra a consequência e corrige com autoridade. Tom de quem já viu isso mil vezes."},
    {"id": "bastidor", "nome": "Bastidores / dia a dia",
     "regra": "Conta um caso real do dia (cliente, situação, conserto), com começo-meio-fim, mostrando o trabalho acontecendo. Humano, próximo, sem discurso."},
    {"id": "depoimento", "nome": "Prova / antes e depois",
     "regra": "Estrutura antes → durante → depois, com detalhes que provam (tempo, valor, o que estava quebrado). Fecha ligando ao próximo cliente."},
    {"id": "promocao", "nome": "Promoção / oferta",
     "regra": "Oferta nos 3 primeiros segundos, condição e prazo claros, um único CTA. Urgência real, sem gritar."},
    {"id": "humor", "nome": "Humor",
     "regra": "Situação reconhecível do público, exagero controlado, punchline curta. O produto entra como solução, não como propaganda."},
]

DURACOES = (15, 30, 45, 60, 90)
OBJETIVOS = {
    "vendas": "gerar vendas ou pedidos de orçamento",
    "seguidores": "ganhar seguidores e engajamento",
    "autoridade": "construir autoridade e confiança",
    "alcance": "alcance máximo: ser visto e compartilhado",
}
GATILHOS: dict[str, str] = {
    "auto": "a IA escolhe o gatilho que mais serve ao tema",
    "curiosidade": "curiosidade / loop aberto (promete algo e só entrega no fim)",
    "dor": "dor específica (o problema que o cliente sente hoje)",
    "prova": "prova social (número, avaliação, caso real do perfil)",
    "escassez": "escassez / urgência real (prazo, vagas, oferta que acaba)",
    "autoridade": "autoridade (quem faz isso todo dia explicando)",
    "contraste": "contraste / antes e depois",
    "identificacao": "identificação ('se você…', o público se vê)",
    "erro": "erro que todo mundo comete (e a correção)",
}

TONS = {
    "direto": "direto, sem rodeio",
    "descontraido": "descontraído, com leveza",
    "serio": "sério e técnico",
    "provocador": "provocador, que cutuca o público",
}


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- empresa
def perfil_empresa(brand_id: str | None) -> dict[str, Any]:
    """O que a IA precisa saber da marca: nome, cartão final e o texto livre
    'sobre a empresa' que o usuário escreve na tela do Roteiro."""
    data = load_brand(brand_id)
    bid = str(data.get("brandId") or brand_id or "padrao")
    copy = _cartao(data.get("endCardCopy"))
    if not any(copy):
        # A marca dele (loja-teste / Prime Camp) tem o cartao VAZIO; quem
        # guarda o "Segue @lojaprimecamp" e o preset ativo. O prompt saiu
        # com "(sem cartao)" na primeira conversa real (03/09).
        try:
            from app.brand_presets import get_active

            ativo = get_active(bid) or {}
            copy = _cartao((ativo.get("style") or ativo).get("endCardCopy"))
        except Exception:  # noqa: BLE001
            pass
    return {
        "brandId": bid,
        "nome": str(data.get("brandName") or "Minha empresa"),
        "cartao": copy,
        "empresa": str(data.get("empresa") or ""),
        "perfil": _perfil_limpo(data.get("perfil")),
        "campos": [{"id": c[0], "rotulo": c[1], "exemplo": c[2]} for c in PERFIL_CAMPOS],
    }


def _cartao(copy: Any) -> list[str]:
    if isinstance(copy, list):
        copy = {"line1": copy[0] if copy else "", "line2": copy[1] if len(copy) > 1 else ""}
    elif isinstance(copy, str):
        copy = {"line1": copy, "line2": ""}
    elif not isinstance(copy, dict):
        copy = {}
    return [str(copy.get("line1") or "").strip(), str(copy.get("line2") or "").strip()]


def salvar_empresa(brand_id: str | None, texto: str) -> dict[str, Any]:
    """Grava só o campo `empresa` da marca (o resto do arquivo fica)."""
    ensure_brands_dir()
    data = load_brand(brand_id)
    bid = str(data.get("brandId") or brand_id or "padrao")
    data["empresa"] = str(texto or "").strip()[:4000]
    path = BRANDS_DIR / f"{_slug(bid)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return perfil_empresa(bid)


# ------------------------------------------------- perfil com campos (4.99)
# "Pegar do preset ou criar um perfil?" (03/09): o preset so guarda estilo,
# nenhum dado do negocio. O perfil mora na MARCA (cada marca tem o seu) e
# vale para o Roteiro hoje e para o resto do pipeline depois.
PERFIL_CAMPOS: list[tuple[str, str, str]] = [
    ("vende", "O que vende / serviços", "Ex.: troca de tela, bateria e conector de iPhone e Android"),
    ("publico", "Para quem", "Ex.: quem quebrou o celular e precisa dele hoje"),
    ("local", "Cidade / região", "Ex.: Campinas, centro"),
    ("diferenciais", "Diferenciais", "Ex.: troca em 40 min na sua frente, garantia de 90 dias"),
    ("provas", "Provas", "Ex.: 900 avaliações no Google nota máxima, 8 anos de loja"),
    ("oferta", "Oferta do momento", "Ex.: película grátis na troca de tela até sexta"),
    ("contato", "Como o cliente fala com você", "Ex.: WhatsApp no link da bio, loja aberta até 18h"),
    ("tom", "Tom de voz", "Ex.: direto, de técnico que explica sem enrolar"),
    ("proibido", "O que NÃO falar", "Ex.: preço fechado, marcas concorrentes, 'mais barato da cidade'"),
]
_PERFIL_IDS = [c[0] for c in PERFIL_CAMPOS]


def _perfil_limpo(bruto: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(bruto, dict):
        for k in _PERFIL_IDS:
            v = bruto.get(k)
            if isinstance(v, list):
                v = "; ".join(str(x) for x in v if str(x).strip())
            v = " ".join(str(v or "").split())[:600]
            if v:
                out[k] = v
    return out


def salvar_perfil(brand_id: str | None, perfil: Any) -> dict[str, Any]:
    ensure_brands_dir()
    data = load_brand(brand_id)
    bid = str(data.get("brandId") or brand_id or "padrao")
    data["perfil"] = _perfil_limpo(perfil)
    path = BRANDS_DIR / f"{_slug(bid)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return perfil_empresa(bid)


def _perfil_em_texto(perfil: dict[str, str], empresa_livre: str) -> str:
    """O perfil como a IA le: uma linha por campo preenchido."""
    linhas = []
    rotulo = {c[0]: c[1] for c in PERFIL_CAMPOS}
    for k in _PERFIL_IDS:
        if perfil.get(k):
            linhas.append(f"- {rotulo[k]}: {perfil[k]}")
    if empresa_livre.strip():
        linhas.append(f"- Observações: {empresa_livre.strip()}")
    return "\n".join(linhas)


def coletar_falas(projects_root: Path | str, brand_id: str, limite: int = 30) -> list[dict[str, str]]:
    """As falas (transcrição do corte) e legendas dos últimos vídeos DESTA
    marca — `edit/preset-used.json` diz de quem é cada projeto."""
    raiz = Path(projects_root)
    if not raiz.exists():
        return []
    alvo = _slug(brand_id or "padrao")
    achados: list[tuple[float, Path]] = []
    for proj in raiz.iterdir():
        edit = proj / "edit"
        cut = edit / "transcripts" / "cut.json"
        if not cut.exists():
            continue
        try:
            usado = json.loads((edit / "preset-used.json").read_text(encoding="utf-8-sig"))
            if _slug(str(usado.get("brandId") or "")) != alvo:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        try:
            achados.append((cut.stat().st_mtime, proj))
        except OSError:
            continue
    achados.sort(key=lambda t: t[0], reverse=True)
    falas: list[dict[str, str]] = []
    vistos: set[str] = set()
    for _, proj in achados:
        if len(falas) >= limite:
            break
        edit = proj / "edit"
        try:
            d = json.loads((edit / "transcripts" / "cut.json").read_text(encoding="utf-8-sig"))
            texto = " ".join(str(d.get("text") or "").split())
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if len(texto) < 20:
            continue
        # As 27 combinacoes do Multiplicador falam quase a mesma coisa: uma
        # basta, senao a ficha nasce de um video so repetido 27 vezes.
        assinatura = texto[:80].lower()
        if assinatura in vistos:
            continue
        vistos.add(assinatura)
        legenda = ""
        try:
            legenda = " ".join((edit / "legenda.txt").read_text(encoding="utf-8-sig").split())[:400]
        except OSError:
            pass
        falas.append({"projeto": proj.name, "texto": texto[:1500], "legenda": legenda})
    return falas


def montar_perfil_pelos_videos(
    projects_root: Path | str,
    brand_id: str,
    *,
    chamar=None,
    limite: int = 30,
) -> dict[str, Any]:
    """Rascunho do perfil a partir do que a empresa JA disse nos vídeos.

    Devolve {"ok", "perfil": {...}, "videos": n, "backend"}; nunca grava —
    quem grava é o usuário depois de corrigir na tela.
    """
    falas = coletar_falas(projects_root, brand_id, limite=limite)
    if not falas:
        raise ValueError("Ainda não há vídeos concluídos desta marca para ler. "
                         "Preencha o perfil à mão por enquanto.")
    perfil = perfil_empresa(brand_id)
    corpo = "\n\n".join(
        f"VÍDEO {i + 1} ({f['projeto']}):\nFALA: {f['texto']}"
        + (f"\nLEGENDA DO POST: {f['legenda']}" if f.get("legenda") else "")
        for i, f in enumerate(falas)
    )
    chaves = ", ".join(f'"{k}"' for k in _PERFIL_IDS)
    rotulos = "\n".join(f"- {k}: {r} ({e})" for k, r, e in PERFIL_CAMPOS)
    messages = [
        {"role": "system", "content": (
            "TAREFA DE TEXTO. Você é um analista que lê transcrições de vídeos de uma "
            "empresa e monta a ficha dela. Responda APENAS um JSON com as chaves "
            f"{chaves}. Cada valor é uma frase curta em português do Brasil, com o que "
            "está EVIDENTE nas falas; o que não aparecer, deixe \"\". Não invente números "
            "nem endereços. Campos:\n" + rotulos)},
        {"role": "user", "content": f"EMPRESA: {perfil.get('nome')}\n\n{corpo[:24000]}"},
    ]
    if chamar is None:
        from app import llm_gateway as gw

        def chamar(msgs):  # noqa: E306
            return gw.chat_com_rede(msgs, "gemini-web/default", json_no_groq=True)

    texto, backend = _chamar_sem_recusa(messages, chamar)
    import sys as _sys

    helpers = str(Path(__file__).resolve().parent.parent / "helpers")
    if helpers not in _sys.path:
        _sys.path.insert(0, helpers)
    from llm_cut_plan import _extract_json  # type: ignore

    try:
        bruto = _extract_json(texto)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("A IA não devolveu a ficha em JSON. Tente de novo.") from e
    rascunho = _perfil_limpo(bruto)
    if not rascunho:
        raise RuntimeError("A IA não achou nada nas falas para preencher. Tente de novo.")
    return {"ok": True, "perfil": rascunho, "videos": len(falas), "backend": backend}


# ----------------------------------------------------------------- prompt
def montar_system(perfil: dict[str, Any], opcoes: dict[str, Any] | None = None) -> str:
    o = opcoes or {}
    estilo = next((e for e in ESTILOS if e["id"] == str(o.get("estilo") or "")), ESTILOS[0])
    dur = int(o.get("duracao") or 30)
    dur = min(DURACOES, key=lambda d: abs(d - dur))
    objetivo = OBJETIVOS.get(str(o.get("objetivo") or ""), OBJETIVOS["vendas"])
    tom = TONS.get(str(o.get("tom") or ""), TONS["direto"])
    gat_id = str(o.get("gatilho") or "auto")
    gatilho = GATILHOS.get(gat_id, GATILHOS["auto"])
    cartao = " / ".join(x for x in perfil.get("cartao") or [] if x)
    empresa = _perfil_em_texto(perfil.get("perfil") or {}, perfil.get("empresa") or "")
    if empresa:
        empresa = "\n" + empresa
    else:
        empresa = "(o usuário ainda não descreveu a empresa — pergunte o essencial em UMA linha só se faltar algo indispensável; senão, assuma o óbvio pelo nome)"
    blocos = max(2, round(dur / 12))
    return (
        "TAREFA DE TEXTO. Você é um REDATOR: escreve o texto que uma pessoa vai ler em voz "
        "alta ao gravar um vídeo curto (Reels, Shorts, TikTok). Você NÃO cria vídeo, imagem "
        "nem áudio — só escreve texto, e isso você faz muito bem. Português do Brasil, como "
        "se fala, para pequenas empresas.\n\n"
        f"EMPRESA: {perfil.get('nome')}\n"
        f"SOBRE A EMPRESA: {empresa}\n"
        f"CARTÃO FINAL DOS VÍDEOS (o que aparece no fim): {cartao or '(sem cartão)'}\n\n"
        f"ESTILO DO VÍDEO: {estilo['nome']} — {estilo['regra']}\n"
        f"DURAÇÃO ALVO: {dur} segundos (cerca de {int(dur * 2.3)} palavras faladas no total).\n"
        f"OBJETIVO: {objetivo}.\nTOM: {tom}.\n"
        f"GATILHO PRINCIPAL: {gatilho}.\n\n"
        "VIRAL QUE VENDE (a regra do jogo):\n"
        "- o vídeo precisa PARAR o scroll e TRAZER cliente — humor sozinho não serve; "
        "piada só entra se carregar a oferta ou a dor;\n"
        "- seja ESPECÍFICO desta empresa: use os dados do perfil (serviço, cidade, prova, "
        "diferencial, oferta) em vez de frases que serviriam para qualquer negócio; "
        "número real do perfil vale mais que adjetivo;\n"
        "- retenção: gancho → promessa/tensão (o que a pessoa ganha ou perde) → entrega "
        "concreta → CTA. Um loop aberto no gancho fecha só no último bloco;\n"
        "- use os gatilhos mentais de propósito: curiosidade, dor específica, prova social, "
        "escassez/urgência REAL (nunca inventada), autoridade, contraste antes/depois, "
        "identificação, erro comum. Cada gancho usa um gatilho diferente;\n"
        "- proibido inventar preço, prazo, número ou promessa que não esteja no perfil "
        "ou no pedido; proibido promessa de cura/ganho garantido.\n\n"
        "REGRAS DO GANCHO (os 2 primeiros segundos decidem tudo):\n"
        "- fale do público, não da empresa; frase curta; concreta; que gere curiosidade, medo de perder, "
        "identificação ou contradição; nada de 'oi gente', nada de apresentação;\n"
        "- proibido começar com 'você sabia'; proibido pergunta genérica;\n"
        "- cada gancho com no máximo 12 palavras, e ao lado, entre colchetes, o gatilho usado. "
        "Ex.: 1. Seu iPhone quebrou e você não pode ficar sem ele hoje. [dor]\n\n"
        "REGRAS DO TEXTO: linguagem falada, frases curtas, sem jargão, sem emoji, sem markdown "
        "(nada de asteriscos, cerquilhas ou listas com hífen), sem aspas em volta das falas. "
        "Números por extenso quando forem falados. Nomes de produto e preço só se o usuário deu.\n\n"
        "FORMATO DA RESPOSTA — exatamente estas seções, nesta ordem, em maiúsculas, "
        "separadas por uma linha em branco:\n\n"
        "GANCHOS\n1. ...\n2. ...\n3. ...\n\n"
        f"ROTEIRO PARA GRAVAR ({dur}s)\n"
        f"Blocos numerados, {blocos} a {blocos + 2} blocos, cada um com o tempo entre parênteses "
        "e a fala em uma linha, começando pelo gancho 1. Ex.: 1. (0-3s) fala...\n\n"
        "CTA\nA frase final, uma linha, ligada ao cartão final da empresa.\n\n"
        "TEXTO NA TELA\nA headline de até 7 palavras para aparecer escrita no vídeo.\n\n"
        "LEGENDA DO POST\nDuas ou três linhas de legenda e, na última linha, 4 a 6 hashtags.\n\n"
        "POR QUE PARA O SCROLL\nUma linha: o gatilho do gancho 1 e o que faz a pessoa ficar até o fim.\n\n"
        "Se o usuário pedir ajuste, devolva o roteiro INTEIRO de novo no mesmo formato, "
        "não só o trecho mudado. Se ele pedir só ganchos, devolva só a seção GANCHOS com 5 opções. "
        "Se ele pedir ÂNGULOS, devolva só a seção ÂNGULOS com 6 itens, um por linha: "
        "nome do ângulo — gatilho — gancho pronto (até 12 palavras)."
    )


def _decorar_pedido(mensagem: str, opcoes: dict[str, Any] | None) -> str:
    """O pedido do usuário, com as opções escolhidas na tela por perto."""
    o = opcoes or {}
    partes = []
    if o.get("nicho"):
        partes.append(f"Nicho/público: {str(o['nicho']).strip()[:200]}")
    corpo = str(mensagem or "").strip()[:MAX_CHARS_MSG]
    return ("\n".join(partes) + "\n\n" if partes else "") + corpo


# ---------------------------------------------------------------- memória
def _pasta(brand_id: str) -> Path:
    p = ROTEIROS_DIR / _slug(brand_id or "padrao")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _caminho(brand_id: str, chat_id: str) -> Path:
    cid = re.sub(r"[^a-z0-9]", "", str(chat_id or "").lower())[:24]
    if not cid:
        raise ValueError("chat inválido")
    return _pasta(brand_id) / f"{cid}.json"


def listar(brand_id: str) -> list[dict[str, Any]]:
    out = []
    for p in _pasta(brand_id).glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "id": d.get("id") or p.stem,
            "titulo": d.get("titulo") or "Roteiro",
            "atualizadoEm": d.get("atualizadoEm") or "",
            "mensagens": len(d.get("mensagens") or []),
        })
    return sorted(out, key=lambda c: str(c.get("atualizadoEm") or ""), reverse=True)


def carregar(brand_id: str, chat_id: str) -> dict[str, Any] | None:
    p = _caminho(brand_id, chat_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def salvar(brand_id: str, chat: dict[str, Any]) -> None:
    chat["atualizadoEm"] = _agora()
    p = _caminho(brand_id, chat["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def apagar(brand_id: str, chat_id: str) -> bool:
    p = _caminho(brand_id, chat_id)
    if p.exists():
        p.unlink()
        return True
    return False


def renomear(brand_id: str, chat_id: str, titulo: str) -> dict[str, Any] | None:
    chat = carregar(brand_id, chat_id)
    if not chat:
        return None
    chat["titulo"] = str(titulo or "").strip()[:80] or chat.get("titulo") or "Roteiro"
    salvar(brand_id, chat)
    return chat


def _titulo_de(mensagem: str) -> str:
    t = " ".join(str(mensagem or "").split())
    return (t[:57] + "…") if len(t) > 60 else (t or "Roteiro")


def novo_chat(brand_id: str, opcoes: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "brandId": brand_id,
        "titulo": "Roteiro",
        "criadoEm": _agora(),
        "atualizadoEm": _agora(),
        "opcoes": dict(opcoes or {}),
        "mensagens": [],
    }


# --------------------------------------------------------------- resposta
def responder(
    brand_id: str,
    mensagem: str,
    *,
    chat_id: str | None = None,
    opcoes: dict[str, Any] | None = None,
    chamar=None,
    groq=None,
) -> dict[str, Any]:
    """Manda o pedido para a IA com a empresa e o histórico; grava e devolve.

    `chamar(messages) -> (texto, backend)` existe para os testes; por padrão
    é a mesma rede do corte (sessão do navegador → Groq). `groq(messages)
    -> texto` é o plano B quando a sessão RECUSA a tarefa (ver
    `_chamar_sem_recusa`).
    """
    mensagem = str(mensagem or "").strip()
    if not mensagem:
        raise ValueError("Escreva o que o vídeo precisa dizer.")
    brand_id = str(brand_id or "padrao")
    chat = carregar(brand_id, chat_id) if chat_id else None
    if chat is None:
        chat = novo_chat(brand_id, opcoes)
        chat["titulo"] = _titulo_de(mensagem)
    if opcoes:
        chat["opcoes"] = dict(opcoes)

    perfil = perfil_empresa(brand_id)
    system = montar_system(perfil, chat.get("opcoes"))
    historico = [
        {"role": m["role"], "content": str(m.get("content") or "")[:MAX_CHARS_MSG]}
        for m in (chat.get("mensagens") or [])[-MAX_HISTORICO:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    pedido = _decorar_pedido(mensagem, chat.get("opcoes"))
    messages = [{"role": "system", "content": system}] + historico + [{"role": "user", "content": pedido}]

    if chamar is None:
        from app import llm_gateway as gw

        def chamar(msgs):  # noqa: E306
            return gw.chat_com_rede(msgs, "gemini-web/default")

    texto, backend = _chamar_sem_recusa(messages, chamar, groq=groq)
    texto = _limpar(str(texto or ""))
    if not texto.strip():
        raise RuntimeError("A IA devolveu vazio. Tente de novo.")

    chat["mensagens"].append({"role": "user", "content": mensagem, "quando": _agora()})
    chat["mensagens"].append({"role": "assistant", "content": texto, "quando": _agora(),
                              "backend": backend})
    salvar(brand_id, chat)
    return {"ok": True, "chat": chat, "resposta": texto, "backend": backend}


_RECUSAS = (
    "não fui programado", "nao fui programado", "consigo gerar texto",
    "modelo de linguagem", "além das minhas", "alem das minhas",
    "não consigo te ajudar", "nao consigo te ajudar", "não posso ajudar",
    "i can't help", "i cannot help", "i'm a language model",
)
REFORCO = (
    "IMPORTANTE: este é um pedido de TEXTO. Você é um redator e vai escrever o texto "
    "de um roteiro falado. Não é para gerar vídeo, imagem ou áudio. Responda com o "
    "texto no formato pedido.\n\n"
)


def recusou(texto: str) -> bool:
    """A sessão do Gemini às vezes responde 'sou um modelo de linguagem, isso
    está além das minhas habilidades' — para um pedido de TEXTO. Aconteceu
    na primeira chamada real do Roteiro (03/09) e já mordia o planejador
    de corte (4.76/4.78)."""
    baixo = " ".join(str(texto or "").lower().split())
    if not baixo:
        return False
    return len(baixo) < 400 and any(m in baixo for m in _RECUSAS)


def _chamar_sem_recusa(messages: list[dict], chamar, groq=None) -> tuple[str, str]:
    """1ª chamada; recusou → repete com o REFORÇO no system; recusou de novo
    → Groq (se houver chave); ainda assim → erro claro para a tela."""
    texto, backend = chamar(messages)
    if not recusou(texto):
        return texto, backend
    if backend != "groq":
        reforcado = [dict(messages[0], content=REFORCO + messages[0]["content"])] + messages[1:]
        print("[roteiro] a sessão recusou a tarefa — repetindo com reforço", flush=True)
        texto, backend = chamar(reforcado)
        if not recusou(texto):
            return texto, backend
    if groq is None:
        from app import llm_gateway as gw

        if gw._groq_key():
            def groq(msgs):  # noqa: E306
                resp = gw._groq_chat(msgs, None)
                return str(resp["choices"][0]["message"]["content"] or "")
    if groq is not None and backend != "groq":
        print("[roteiro] a sessão recusou duas vezes — indo para o Groq", flush=True)
        texto = groq(messages)
        if not recusou(texto):
            return texto, "groq"
    raise RuntimeError(
        "A IA recusou escrever o roteiro. Tente de novo em instantes, ou abra a "
        "sessão do Gemini no navegador e recapture em IA.")


def _limpar(texto: str) -> str:
    """Tira o markdown que o modelo insiste em pôr (asteriscos, cerquilhas,
    crases) — o roteiro é para ler no teleprompter, não numa página."""
    t = texto.replace("\r\n", "\n")
    t = re.sub(r"```[a-z]*\n?", "", t)
    # cabecalho markdown e "# " com espaco; "#trocadetela" e hashtag e fica
    # (a primeira chamada real perdeu o "#" de "#campinas" por causa disto)
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", t)
    t = re.sub(r"(?m)^\s*[-•]\s+", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


SECOES = ("GANCHOS", "ROTEIRO PARA GRAVAR", "CTA", "TEXTO NA TELA", "LEGENDA DO POST",
          "POR QUE PARA O SCROLL", "ÂNGULOS", "ANGULOS")


def _e_cabecalho(linha: str) -> str | None:
    cab = linha.strip().upper().rstrip(":")
    for s in SECOES:
        if cab == s or cab.startswith(s + " ") or cab.startswith(s + "("):
            return s
    return None


def secao(texto: str, nome: str) -> str:
    """Só uma seção da resposta (ex.: GANCHOS) — para o botão de copiar."""
    out: list[str] = []
    dentro = False
    alvo = nome.strip().upper()
    for ln in texto.split("\n"):
        cab = _e_cabecalho(ln)
        if cab is not None:
            if dentro:
                break
            dentro = cab == alvo
            continue
        if dentro:
            out.append(ln)
    return "\n".join(out).strip()
