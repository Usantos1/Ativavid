"""Preset curto do usuário não apaga o texto do card final."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.local_server import merge_preset


def test_stub_keeps_end_card():
    shipped = {
        "brandName": "Padrão",
        "endCardCopy": {"line1": "Segue @loja", "line2": "direct"},
        "elements": {"endCard": True, "musicAI": True},
    }
    user = {"brandName": "Prime Camp", "brandId": "loja-teste", "fastMode": True}
    got = merge_preset(shipped, user)
    assert got["brandName"] == "Prime Camp"
    assert got["endCardCopy"]["line1"] == "Segue @loja"
    assert got["elements"]["endCard"] is True


if __name__ == "__main__":
    test_stub_keeps_end_card()
    print("ok")
