#!/usr/bin/env python3
"""Diz, em portugues, o que falta pra editar — e o que fazer pra resolver.

Diferente do selftest.py, que testa o CODIGO da skill. Este testa a MAQUINA:
ffmpeg, node, chaves, espaco em disco, servidores esquecidos rodando. E a
diferenca importa porque as duas coisas quebram por motivos diferentes e quem
conserta cada uma e uma pessoa diferente.

A regra deste arquivo: **nenhuma mensagem de erro tecnica**. Um traceback nao
ajuda quem nao programa — ele so informa que algo deu errado, que a pessoa ja
sabia. Todo problema aqui responde tres coisas: o que falta, por que isso
importa pro video, e o comando exato pra resolver.

    python helpers/doutor.py            # diagnostico
    python helpers/doutor.py --json     # pra outro programa consumir

Codigo de saida = quantidade de problemas que BLOQUEIAM. Avisos nao contam,
porque a maioria e opcional e travar por causa deles seria mentira.
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))
try:
    from app.win_process import hide_console_kwargs
except Exception:  # noqa: BLE001
    def hide_console_kwargs() -> dict:  # type: ignore[misc]
        return {}

OK, AVISO, BLOQUEIO = "ok", "aviso", "bloqueio"
_itens: list[dict] = []


def diz(nivel: str, titulo: str, detalhe: str = "", solucao: str = "",
        acao: str = "", acao_texto: str = "") -> None:
    """Uma linha do diagnostico.

    `acao` e o unico campo que a TELA transforma em botao (5.0.25). Ele
    pediu: "aqui nao deveria mostrar se a IA local esta instalada... porque
    assim o cliente poderia baixar por aqui nessa checagem". Sem isso o
    diagnostico so sabia dizer em que menu procurar.
    """
    _itens.append({"nivel": nivel, "titulo": titulo, "detalhe": detalhe,
                   "solucao": solucao, "acao": acao, "acaoTexto": acao_texto})


def versao(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace", **hide_console_kwargs())
        primeira = (r.stdout or r.stderr or "").strip().splitlines()
        return primeira[0][:70] if primeira else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ----------------------------------------------------------------- programas
def checar_programas() -> None:
    # ffmpeg/ffprobe: sem eles nao existe Fase 1. Nada a jusante adianta.
    for prog, pra_que in (("ffmpeg", "cortar e renderizar o video"),
                          ("ffprobe", "medir duracao e formato dos arquivos")):
        caminho = shutil.which(prog)
        if caminho:
            diz(OK, f"{prog} instalado", versao([prog, "-version"]))
        else:
            diz(BLOQUEIO, f"{prog} nao encontrado",
                f"E ele que faz {pra_que} — sem isso nenhum video sai.",
                "winget install Gyan.FFmpeg\n"
                "Depois FECHE e abra o terminal de novo (o PATH so atualiza em janela nova).")

    # node: so a Fase 2. Da pra entregar um corte limpo sem ele, entao avisa.
    if shutil.which("node"):
        v = versao(["node", "--version"])
        maior = 0
        try:
            maior = int(v.lstrip("v").split(".")[0])
        except (ValueError, IndexError):
            pass
        if maior and maior < 18:
            diz(BLOQUEIO, f"Node muito antigo ({v})",
                "O Remotion (legendas, headline, inserts) precisa da versao 18 ou maior.",
                "winget install OpenJS.NodeJS.LTS")
        else:
            diz(OK, "Node instalado", v)
    else:
        diz(AVISO, "Node nao encontrado",
            "Sem ele o corte e a cor funcionam, mas o video sai SEM legenda, "
            "sem headline e sem imagens — a Fase 2 inteira nao roda.",
            "winget install OpenJS.NodeJS.LTS")


# -------------------------------------------------------------------- chaves
def _ler_env(arq: Path, valores: dict[str, str]) -> None:
    """Le um .env para dentro de `valores` SEM sobrescrever o que ja veio
    (a primeira fonte da ordem vence, igual ao app)."""
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, _, v = linha.partition("=")
            if v.strip():
                valores.setdefault(k.strip(),
                                   v.strip().strip('"').strip("'"))


def checar_chaves() -> None:
    # ORDEM DO APP: %USERPROFILE%\ATIVAVID\.env primeiro (Program Files e
    # so leitura, entao e ali que a tela de Integracoes grava), depois o
    # .env legado ao lado do codigo. Ate 27/08 o Doutor so olhava o legado:
    # numa instalacao normal ele NUNCA achava as chaves e acusava "Sem
    # chave da ElevenLabs" com a chave configurada e funcionando. Aviso
    # falso no diagnostico e pior que aviso nenhum — manda o cliente (e a
    # mim) caçar fantasma.
    valores: dict[str, str] = {}
    _ler_env(Path.home() / "ATIVAVID" / ".env", valores)
    _ler_env(SKILL / ".env", valores)
    for k in ("GROQ_API_KEY", "PEXELS_API_KEY"):
        if os.environ.get(k):
            valores.setdefault(k, os.environ[k])

    # A transcricao NAO depende de chave nenhuma: ela roda na propria
    # maquina (faster-whisper local, padrao desde 21/08/2026). E a trilha
    # tambem nao: o ElevenLabs saiu do produto em 02/09/2026 — quem compoe
    # e a IA local (MusicGen), com a Biblioteca de trilhas de reserva.
    # Cobrar chave aqui viraria aviso falso, que ensina a ignorar o
    # relatorio.
    diz(OK, "Transcricao roda nesta maquina",
        "Nao precisa de conta, chave nem internet depois que os componentes "
        "locais estiverem instalados.")

    if not valores.get("PEXELS_API_KEY"):
        diz(AVISO, "Sem chave da Pexels",
            "So afeta as imagens ilustrativas de banco. O video sai normal sem elas.",
            "Escreva PEXELS_API_KEY=... no arquivo .env (gratis em pexels.com/api)")


# ------------------------------------------------------------------- espaco
def checar_espaco() -> None:
    """Espaco onde o trabalho REALMENTE acontece, nao onde a skill mora.

    A primeira versao olhava so o disco da skill (C:) e cravou "pouco espaco"
    com 7 GB — enquanto os videos ficam no E:, com 700 GB livres. O aviso
    estava tecnicamente certo e praticamente errado, que e a pior combinacao:
    manda a pessoa liberar espaco que nao esta faltando, e ela aprende a
    ignorar o diagnostico. Os recortes e o render nascem ao lado do video, no
    disco do PROJETO.
    """
    # `~/ATIVAVID` entra na lista: na maquina do usuario ele esta noutro
    # disco (C:, com 7% livres) e guarda 1,9 GB de modelos de transcricao,
    # o cache do Remotion, a Biblioteca e o instalador que a atualizacao
    # baixa. Cheio ele, a transcricao nao carrega o modelo e a atualizacao
    # nao baixa — e o diagnostico dizia "tudo certo", porque so media o
    # disco dos projetos.
    dados = Path.home() / "ATIVAVID"
    alvos: dict[str, Path] = {}
    para_que: dict[str, str] = {}
    for p, papel in ((Path.cwd(), "onde voce esta editando"),
                     (SKILL, "onde a skill esta"),
                     (dados, "modelos, biblioteca e atualizacao")):
        try:
            existe = p.exists()
        except OSError:
            existe = False
        if not existe:
            continue
        d = (p.drive or str(p)).rstrip(":") or str(p)
        if alvos.setdefault(d, p) is p:
            para_que[d] = papel

    for letra, caminho in alvos.items():
        try:
            livre = shutil.disk_usage(str(caminho)).free / (1024 ** 3)
        except OSError:
            continue
        onde = para_que.get(letra) or "onde voce esta editando"
        # um reel de 60s gera fonte + extracts por segmento + cut + render
        # final; 5 GB e o piso pra um video sem sustos, nao uma media
        if livre < 5:
            diz(BLOQUEIO, f"Disco {letra}: quase cheio ({livre:.1f} GB livres, {onde})",
                "Um video precisa de uns 5 GB de folga entre os recortes e o "
                "render. Com menos que isso o render morre no meio, depois de "
                "ja ter demorado.",
                "Libere espaco e rode de novo.")
        elif livre < 20:
            diz(AVISO, f"Disco {letra}: pouco espaco ({livre:.1f} GB livres, {onde})",
                "Da pra um ou dois videos. Em lote vai faltar no meio.")
        else:
            diz(OK, f"Disco {letra}: {livre:.0f} GB livres ({onde})")


# ------------------------------------------------------- processos esquecidos
def checar_processos() -> None:
    """Servidores e vigias vivos apontando pra pasta que nao existe mais.

    Isso ja aconteceu de verdade nesta maquina: 21 processos orfaos. Um vigia
    esquecido e pior do que inutil — ele fica armado num projeto terminado e
    aplica sozinho a proxima coisa que alguem salvar.
    """
    if os.name != "nt":
        return
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'preview_server|watch_edits' } | "
             "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=25, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", **hide_console_kwargs())
    except (OSError, subprocess.SubprocessError):
        return
    linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    if not linhas:
        diz(OK, "Nenhum servidor de preview rodando")
        return

    orfaos = []
    for linha in linhas:
        pid, _, cmd = linha.partition("|")
        # o caminho vem depois de --root, entre aspas quando tem espaco
        import re
        m = re.search(r'--root\s+"([^"]+)"|--root\s+(\S+)', cmd)
        alvo = (m.group(1) or m.group(2)) if m else None
        if not alvo:
            m2 = re.search(r'watch_edits\.py"?\s+"?([^"]+?)"?\s*$', cmd)
            alvo = m2.group(1) if m2 else None
        if alvo and not Path(alvo).exists():
            orfaos.append((pid.strip(), alvo))

    vivos = len(linhas) - len(orfaos)
    if vivos:
        diz(OK, f"{vivos} processo(s) de preview ativo(s)")
    if orfaos:
        # /PID tem de vir repetido antes de CADA numero. Escrito como
        # "taskkill /F /PID a b c" o comando falha inteiro em "Argumento
        # invalido" e nao mata nada — o que, pra quem nao programa, se parece
        # exatamente com "rodei e continuou lá". Testado nas duas formas.
        pids = " ".join(f"/PID {p}" for p, _ in orfaos)
        diz(AVISO, f"{len(orfaos)} processo(s) apontando pra pasta que nao existe mais",
            "Sobraram de projetos apagados. Um vigia esquecido pode aplicar "
            "sozinho a proxima coisa que voce salvar no preview.",
            f"Feche assim:\n  taskkill /F {pids}")


# -------------------------------------------------------------------- python
def checar_python() -> None:
    faltando = []
    for mod, pra_que in (("requests", "falar com as APIs de transcricao e imagens"),
                         ("PIL", "montar as grades de conferencia"),
                         ("numpy", "medir o nivel da voz")):
        try:
            __import__(mod)
        except ImportError:
            faltando.append((mod, pra_que))
    if faltando:
        diz(BLOQUEIO, "Faltam bibliotecas do Python",
            "Sem elas varios passos param: " + "; ".join(f"{m} ({p})" for m, p in faltando),
            f"cd {SKILL}\nuv sync")
    else:
        diz(OK, "Bibliotecas do Python instaladas")


def checar_sistema() -> None:
    try:
        sys.path.insert(0, str(SKILL))
        from app.system_info import detect_machine
        from app.performance import profile_settings

        m = detect_machine()
        perf = profile_settings("auto", m)
        diz(OK, f"Sistema {m.get('os')} {m.get('osRelease')}",
            f"CPU {m.get('cores')} núcleos · RAM {m.get('ramGb')} GB "
            f"({m.get('ramFreeGb')} livres) · Disco projetos {m.get('diskFreeGb')} GB")
        # Memoria LIVRE, nao total. A maquina de uma cliente (04/09) tinha
        # 7,6 GB com 0,9 livre: o render abre um navegador inteiro para
        # desenhar, e com menos de ~2,5 GB ele morre no meio sem dizer por
        # que — o job cai para o caminho lento ou falha. O numero total
        # aparecia na linha de cima e nao acusava nada.
        try:
            livre = float(m.get("ramFreeGb") or 0)
        except (TypeError, ValueError):
            livre = 0.0
        if 0 < livre < 2.5:
            diz(AVISO, f"Pouca memória livre: {livre:.1f} GB",
                "O render abre um navegador inteiro para desenhar as "
                "legendas e precisa de uns 2,5 GB livres; com menos, o "
                "vídeo pode falhar no meio ou sair pelo caminho lento.",
                "Feche navegadores e outros programas antes de editar. "
                "Se for sempre assim, a máquina precisa de mais memória.")
        accel = m.get("accel") or {}
        enc = accel.get("preferredEncoder") or "libx264"
        if enc != "libx264":
            diz(OK, f"Aceleração de vídeo: {enc}", f"Modo {accel.get('mode')}")
        else:
            diz(AVISO, "Renderização em CPU (libx264)",
                "Sem NVENC/QSV/AMF detectado no ffmpeg — funciona, mas fica mais lento.")
        diz(OK, f"Perfil automático: {perf.get('label')}",
            f"Jobs paralelos={perf.get('parallelJobs')} · encoder={perf.get('encoder')}")
        gpus = m.get("gpus") or []
        if gpus:
            for g in gpus[:3]:
                diz(OK, f"GPU: {g.get('name')}", f"VRAM≈{g.get('vramGb')} GB" if g.get("vramGb") else "")
    except Exception as e:  # noqa: BLE001
        diz(AVISO, "Não consegui ler o hardware", str(e)[:120])


def checar_caminho_de_pagamento() -> None:
    """Quem esbarrar no bloqueio tem como pagar?

    O botao "Assinar agora" do app so aparece quando existe `checkoutUrl`
    — e ele vive no `license_config.json`, o arquivo que vai dentro de
    CADA instalacao. Em 31/08 esse campo estava vazio na build: o cliente
    com trial vencido via a janela da licenca sem uma forma de comprar, e
    nada na tela dizia isso a ele nem a mim.
    """
    try:
        sys.path.insert(0, str(SKILL))
        from app import settings_store as ss

        url = str(ss.load_settings().get("checkoutUrl") or "").strip()
        empacotado = str(
            (ss.bundled_license_config() or {}).get("checkoutUrl") or "").strip()
    except Exception as e:  # noqa: BLE001
        diz(AVISO, "Nao consegui ler o caminho de pagamento", str(e)[:120])
        return
    if not url:
        diz(AVISO, "Sem link de pagamento",
            "Quem estiver com o trial vencido nao ve botao de comprar. "
            "Configure o checkoutUrl.")
        return
    if not empacotado:
        diz(AVISO, "Link de pagamento so nesta maquina",
            "O `license_config.json` da build esta sem checkoutUrl: os "
            "clientes que instalarem nao verao o botao de comprar.")
        return
    diz(OK, "Caminho de pagamento no lugar", url[:48] + ("..." if len(url) > 48 else ""))


def checar_motor_rapido() -> None:
    """O desenho rapido esta ligado?

    Ele e 3,3x mais rapido (421s contra 1383s de media nos 413 jobs
    registrados). Uma pausa do canary grava `overlayRollout=off` e, dai em
    diante, TODO video sai pelo caminho completo — sem nada na tela. Na
    maquina do usuario havia uma pausa de "TRUE_PEAK -0,9" e quatro videos
    lentos por causa dela.
    """
    try:
        sys.path.insert(0, str(SKILL))
        from app.overlay_path import overlay_rollout
    except Exception as e:  # noqa: BLE001
        diz(AVISO, "Nao consegui ler o modo do desenho", str(e)[:120])
        return
    modo = overlay_rollout()
    pausa = {}
    try:
        from app.overlay_canary import load_state

        st = load_state() or {}
        if st.get("paused"):
            pausa = {"motivo": str(st.get("pausedReason") or "sem motivo"),
                     "quando": str(st.get("pausedAt") or "")}
    except Exception:  # noqa: BLE001
        pass

    # A pausa e o freio do modo CANARIO: `canary_allows_attempt` so a
    # consulta quando `overlayRollout == "canary"`. Em `default` ela nao
    # segura nada, e mesmo assim o diagnostico dizia "Desenho rapido
    # pausado" — mandando procurar defeito onde nao havia. Na maquina dele
    # o aviso aparecia com uma pausa sem data (anterior a folga de pico) e
    # os videos daquele mesmo dia saindo pelo motor proprio.
    if modo == "default":
        detalhe = "Videos saem pelo motor proprio."
        if pausa:
            detalhe += (" Ha uma pausa anotada"
                        + (f" de {pausa['quando'][:10]}" if pausa["quando"]
                           else " sem data (antiga)")
                        + f", '{pausa['motivo']}', que so valeria no modo canario.")
        diz(OK, "Desenho rapido ligado", detalhe)
        return
    if modo == "off":
        detalhe = "Todo video sai pelo caminho completo, cerca de 3x mais lento."
        if pausa:
            detalhe += (f" Foi desligado por '{pausa['motivo']}'"
                        + (f" em {pausa['quando'][:10]}" if pausa["quando"] else "")
                        + ".")
        diz(AVISO, "Desenho rapido DESLIGADO", detalhe,
            "Configuracoes > Avancado > Motor de render: Automatico.")
        return
    if pausa:
        diz(AVISO, "Desenho rapido pausado",
            f"Motivo: {pausa['motivo']}"
            + (f" ({pausa['quando'][:10]})" if pausa["quando"] else ""),
            "Se o defeito ja foi corrigido, o modo Automatico volta a usa-lo.")
        return
    diz(OK, f"Desenho rapido em modo {modo}")


def checar_pecas_opcionais() -> None:
    """O que da para instalar nesta maquina — e que ainda nao esta aqui.

    O instalador tem ~7 MB de proposito: transcricao local e IA de musica
    sao baixadas depois, sob demanda. Quem nunca abriu Configuracoes nao
    sabe que existem, e o diagnostico — que e a primeira tela que o cliente
    abre quando algo nao sai como esperava — nao falava delas.
    """
    try:
        sys.path.insert(0, str(SKILL))
        from app import musica_local
    except Exception as e:  # noqa: BLE001
        diz(AVISO, "Nao consegui checar a IA local de musica", str(e)[:120])
        return

    try:
        est = musica_local.estado()
    except Exception as e:  # noqa: BLE001
        diz(AVISO, "Nao consegui checar a IA local de musica", str(e)[:120])
        return

    gb = f"{est.get('mbTotal', 4800) / 1000:.1f}".replace(".", ",")
    placa = str(est.get("gpuNome") or "")
    # Sem a IA local, a trilha vem da Biblioteca — e a pasta nasce VAZIA.
    # Maquina sem NVIDIA e sem MP3 = video mudo de musica, e a tela nao
    # dizia isso em lugar nenhum (cliente com Intel UHD, 04/09). O pacote de
    # trilhas e efeitos (5.0.29) resolve com um clique.
    if not est.get("instalado"):
        try:
            from app.broll_library import library_root

            pasta = library_root() / "Trilhas"
            faixas = sum(1 for f in pasta.rglob("*")
                         if f.is_file() and f.suffix.lower()
                         in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"))
        except Exception:  # noqa: BLE001 — pasta ilegivel nao derruba o check
            faixas = -1
        if faixas == 0:
            diz(AVISO, "Biblioteca de trilhas vazia",
                "Sem a IA local de musica, a trilha de cada video vem daqui — "
                "e nao ha nenhuma. O video sai sem musica.",
                acao="baixar_pacote", acao_texto="Baixar trilhas e efeitos")
    if est.get("instalado"):
        diz(OK, "IA local de musica instalada",
            f"{est.get('gb', 0)} GB em {est.get('pasta')}. "
            "Compoe a trilha de cada video sem gastar creditos.")
    elif not est.get("gpu"):
        diz(AVISO, "IA local de musica indisponivel",
            ("Precisa de placa NVIDIA"
             + (f" — aqui encontrei {placa}." if placa
                else " — nao encontrei placa aqui.")
             + " Sem ela a trilha vem da sua Biblioteca."),
            "Deixe MP3s em ATIVAVID/Biblioteca/Trilhas para o video nao "
            "sair mudo de musica.")
    elif est.get("incompleta"):
        diz(AVISO, "IA local de musica pela metade",
            "Um download anterior parou no meio; da para continuar de onde "
            "parou.", acao="instalar_musica",
            acao_texto="Continuar instalacao")
    else:
        # O que faria o download FALHAR depois do clique. Oferecer um botao
        # que morre no meio e pior que nao oferecer nada: o cliente espera
        # gigabytes e recebe um erro.
        falta = _o_que_falta_para_baixar(est)
        detalhe = (f"Sao {gb} GB, baixados uma vez so"
                   + (f". Placa encontrada: {placa}." if placa else ".")
                   + " Sem ela a trilha vem da sua Biblioteca.")
        if falta:
            diz(AVISO, "IA local de musica nao instalada",
                detalhe + " " + falta[0], falta[1])
            return
        diz(AVISO, "IA local de musica nao instalada", detalhe,
            acao="instalar_musica", acao_texto="Instalar aqui")


def _o_que_falta_para_baixar(est: dict) -> tuple[str, str] | None:
    """(o que esta faltando, como resolver) — ou None se da para baixar."""
    if not est.get("uv"):
        return ("Falta o `uv`, que monta o ambiente do motor.",
                "Reinstale o ATIVAVID: o instalador traz o uv junto.")
    # ~4,8 GB de download + o venv descompactado; 7 GB e o piso sem susto
    try:
        alvo = Path(str(est.get("pasta") or ""))
        base = alvo if alvo.exists() else alvo.parent
        while not base.exists() and base != base.parent:
            base = base.parent
        livre = shutil.disk_usage(str(base)).free / (1024 ** 3)
    except (OSError, ValueError):
        return None
    if livre < 7:
        return (f"So ha {livre:.1f} GB livres em {alvo.drive or alvo}.",
                "Libere uns 7 GB nesse disco (Configuracoes > Liberar espaco) "
                "e cheque de novo.")
    return None


def main() -> int:
    # Sem argparse (nao ha flags de verdade a parsear), mas --help tem de
    # responder como em todo helper daqui: o selftest cobra isso de todos, e
    # foi ele que pegou este arquivo rodando o diagnostico inteiro quando lhe
    # pediram ajuda — e devolvendo o numero de bloqueios como se fosse erro.
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__ or "uso: doutor.py [--json]")
        return 0

    for fn in (checar_programas, checar_sistema, checar_motor_rapido,
               checar_pecas_opcionais, checar_caminho_de_pagamento,
               checar_chaves, checar_python, checar_espaco, checar_processos):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — um check quebrado nao pode derrubar o diagnostico
            diz(AVISO, f"Nao consegui checar {fn.__name__.replace('checar_', '')}",
                f"{type(e).__name__}: {e}")

    bloqueios = [i for i in _itens if i["nivel"] == BLOQUEIO]
    avisos = [i for i in _itens if i["nivel"] == AVISO]

    if "--json" in sys.argv:
        print(json.dumps({"itens": _itens, "bloqueios": len(bloqueios),
                          "avisos": len(avisos)}, ensure_ascii=False, indent=2))
        return len(bloqueios)

    print("\nATIVAVID — diagnostico\n")
    for i in _itens:
        if i["nivel"] == OK:
            print(f"  ok    {i['titulo']}" + (f"  ({i['detalhe']})" if i["detalhe"] else ""))
    for rotulo, grupo in (("PRECISA RESOLVER", bloqueios), ("DA PRA VIVER SEM", avisos)):
        if not grupo:
            continue
        print(f"\n{rotulo}\n")
        for i in grupo:
            print(f"  {i['titulo']}")
            if i["detalhe"]:
                print(f"     {i['detalhe']}")
            if i["solucao"]:
                for ln in i["solucao"].splitlines():
                    print(f"     > {ln}")
            print()

    if bloqueios:
        print(f"{len(bloqueios)} coisa(s) impedem de editar. Resolva as de cima e rode de novo.\n")
    elif avisos:
        print("Da pra editar. Os avisos acima sao recursos opcionais.\n")
    else:
        print("Tudo pronto pra editar.\n")
    return len(bloqueios)


if __name__ == "__main__":
    sys.exit(main())
