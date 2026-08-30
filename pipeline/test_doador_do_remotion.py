# -*- coding: utf-8 -*-
"""O node_modules doador sai da pasta de projetos CONFIGURADA.

Para não pagar um `npm install` inteiro, o app procura um `node_modules`
já pronto num projeto existente e copia. A lista de onde procurar começava
com um caminho fixo de UMA máquina — a pasta de projetos deste
usuário, escrita à mão no código.

Quem instalasse o app com a pasta de projetos noutro lugar não achava
doador nenhum e pagava o `npm install` completo. E o app é revendido: a
máquina do cliente nunca é esta.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RC = (REPO / "app" / "remotion_cache.py").read_text(encoding="utf-8")


def test_a_pasta_configurada_vem_primeiro():
    i = RC.index("def _seed_from_donor(")
    corpo = RC[i:i + 1400]
    assert "load_settings" in corpo and "projectsRoot" in corpo
    assert corpo.index("projectsRoot") < corpo.index('"ATIVAVID" / "Projetos"')


def test_o_caminho_de_uma_maquina_so_saiu_do_codigo():
    i = RC.index("def _seed_from_donor(")
    corpo = RC[i:i + 1400]
    # só no comentário que explica por que saiu
    linhas = [l for l in corpo.splitlines()
              if "ATIVAVID" in l and "Projetos" in l
              and not l.strip().startswith("#")]
    assert all("Path.home()" in l for l in linhas), linhas


def test_ler_a_configuracao_nunca_derruba():
    i = RC.index("def _seed_from_donor(")
    corpo = RC[i:i + 1400]
    assert "except Exception" in corpo


def test_a_casa_continua_como_reserva():
    """Instalação sem configuração ainda precisa de um lugar para olhar."""
    i = RC.index("def _seed_from_donor(")
    corpo = RC[i:i + 1400]
    assert 'Path.home() / "ATIVAVID" / "Projetos"' in corpo
