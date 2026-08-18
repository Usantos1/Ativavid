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


def test_empty_copy_in_overlay_does_not_wipe():
    shipped = {"endCardCopy": {"line1": "Segue @loja", "line2": "direct"}}
    user = {"endCardCopy": {"line1": "", "line2": ""}, "brandName": "X"}
    got = merge_preset(shipped, user)
    assert got["endCardCopy"]["line1"] == "Segue @loja"
    assert got["brandName"] == "X"


def test_fill_end_card_from_padrao():
    from app.brand_kits import fill_end_card_copy
    import json as _json

    got = fill_end_card_copy({"brandId": "loja-teste", "fastMode": True})
    assert "lojaprimecamp" not in _json.dumps(got)
    got2 = fill_end_card_copy({"endCardCopy": {"line1": "Já tenho", "line2": ""}})
    assert got2["endCardCopy"]["line1"] == "Já tenho"


if __name__ == "__main__":
    test_stub_keeps_end_card()
    test_empty_copy_in_overlay_does_not_wipe()
    test_fill_end_card_from_padrao()
    print("ok")
