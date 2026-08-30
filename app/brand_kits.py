"""Brand kits multi-marca + presets de export.

Marcas ficam em %USERPROFILE%/ATIVAVID/brands (gravável).
O pacote em Program Files só fornece a semente "Padrão".
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PKG_BRANDS = REPO / "assets" / "brands"
PREVIEW = REPO / "assets" / "preview"
USER_DIR = Path.home() / "ATIVAVID"
BRANDS_DIR = USER_DIR / "brands"
ACTIVE_PATH = BRANDS_DIR / "active.json"
USER_PRESET = USER_DIR / "default-style.json"

EXPORT_PRESETS = {
    "reels": {
        "id": "reels",
        "label": "Reels / Shorts / TikTok",
        "aspect": "9:16",
        "width": 1080,
        "height": 1920,
        "videoGoal": "reels",
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube 16:9",
        "aspect": "16:9",
        "width": 1920,
        "height": 1080,
        "videoGoal": "youtube",
    },
    "square": {
        "id": "square",
        "label": "Quadrado 1:1",
        "aspect": "1:1",
        "width": 1080,
        "height": 1080,
        "videoGoal": "anuncio",
    },
    "feed": {
        "id": "feed",
        "label": "Feed 4:5",
        "aspect": "4:5",
        "width": 1080,
        "height": 1350,
        "videoGoal": "reels",
    },
}


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower(), flags=re.UNICODE)
    return (s.strip("-") or "marca")[:40]


def ensure_brands_dir() -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)

    seed = BRANDS_DIR / "padrao.json"
    if not seed.exists():
        pkg = PKG_BRANDS / "padrao.json"
        default = PREVIEW / "default-style.json"
        if pkg.exists():
            shutil.copy2(pkg, seed)
        elif default.exists():
            data = json.loads(default.read_text(encoding="utf-8-sig"))
            data["brandId"] = "padrao"
            data["brandName"] = data.get("brandName") or "Padrão"
            seed.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            seed.write_text(
                json.dumps({
                    "brandId": "padrao",
                    "brandName": "Padrão",
                    "exportPreset": "reels",
                    "endCardCopy": {"line1": "", "line2": ""},
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    # Garante brandName legível no seed
    try:
        data = json.loads(seed.read_text(encoding="utf-8-sig"))
        if not data.get("brandName"):
            data["brandName"] = "Padrão"
            data["brandId"] = data.get("brandId") or "padrao"
            seed.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass

    if not ACTIVE_PATH.exists():
        ACTIVE_PATH.write_text(
            json.dumps({"activeId": "padrao"}, indent=2) + "\n", encoding="utf-8"
        )


def list_brands() -> list[dict[str, Any]]:
    ensure_brands_dir()
    active = get_active_id()
    out: list[dict[str, Any]] = []
    for p in sorted(BRANDS_DIR.glob("*.json")):
        if p.name == "active.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        bid = str(data.get("brandId") or p.stem)
        out.append({
            "id": bid,
            "name": data.get("brandName") or bid,
            "active": bid == active,
            "endCardCopy": data.get("endCardCopy"),
            "accent": data.get("accent"),
            "exportPreset": data.get("exportPreset") or "reels",
            # O ESTILO inteiro vai junto: e o que permite trocar a marca de um
            # video ja criado sem reimportar (a tela aplica isto no editor).
            # Sem ele so dava para ver o nome — e o video seguia com as cores
            # e o CTA da marca antiga, que foi o caso de 29/08.
            "style": {k: v for k, v in data.items()
                      if k not in ("brandId", "brandName")},
        })
    if not out:
        out.append({
            "id": "padrao",
            "name": "Padrão",
            "active": True,
            "exportPreset": "reels",
        })
    return out


def get_active_id() -> str:
    ensure_brands_dir()
    try:
        return str(json.loads(ACTIVE_PATH.read_text(encoding="utf-8-sig")).get("activeId") or "padrao")
    except (OSError, json.JSONDecodeError):
        return "padrao"


def end_card_copy_filled(copy: object) -> bool:
    if not isinstance(copy, dict):
        return False
    return bool(str(copy.get("line1") or "").strip() or str(copy.get("line2") or "").strip())


def shipped_end_card_copy() -> dict[str, str]:
    """Texto do card final do preset empacotado — não o stub curto do usuário."""
    for path in (PKG_BRANDS / "padrao.json", PREVIEW / "default-style.json"):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        copy = data.get("endCardCopy") if isinstance(data, dict) else None
        if end_card_copy_filled(copy):
            return {
                "line1": str(copy.get("line1") or ""),
                "line2": str(copy.get("line2") or ""),
            }
    return {"line1": "", "line2": ""}


def fill_end_card_copy(preset: dict | None) -> dict:
    """Se o card final está vazio, usa o texto empacotado. Não apaga o que já tem."""
    out = dict(preset or {})
    if end_card_copy_filled(out.get("endCardCopy")):
        return out
    out["endCardCopy"] = shipped_end_card_copy()
    return out


def load_brand(brand_id: str | None = None) -> dict[str, Any]:
    ensure_brands_dir()
    bid = brand_id or get_active_id()
    path = BRANDS_DIR / f"{_slug(bid)}.json"
    if not path.exists():
        path = BRANDS_DIR / "padrao.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    d = PREVIEW / "default-style.json"
    if d.exists():
        return json.loads(d.read_text(encoding="utf-8-sig"))
    return {"brandId": "padrao", "brandName": "Padrão", "exportPreset": "reels"}


def _slug_livre(base: str, name: str) -> str:
    """Slug que nao ATROPELA outra marca.

    `save_brand` derivava o slug do nome quando nao vinha `brandId`. Se o slug
    ja estivesse ocupado por uma marca com OUTRO nome, a gravacao substituia
    aquele arquivo — a marca antiga sumia e nenhuma nova aparecia, com o toast
    dizendo "Marca salva e ativada". Aconteceu duas vezes nesta maquina:
    `brands/loja-teste.json` ficou chamando "Prime Camp" e `brands/padrao.json`
    ficou chamando "Uander" — nos dois o nome de exibicao discorda do arquivo,
    que e a assinatura do atropelo.
    """
    alvo = BRANDS_DIR / f"{base}.json"
    if not alvo.exists():
        return base
    try:
        atual = json.loads(alvo.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return base
    if str(atual.get("brandName") or "").strip() == name:
        return base            # mesma marca: e atualizacao, nao criacao
    n = 2
    while (BRANDS_DIR / f"{base}-{n}.json").exists() and n < 100:
        n += 1
    return f"{base}-{n}"


def save_brand(body: dict[str, Any]) -> dict[str, Any]:
    ensure_brands_dir()
    name = str(body.get("brandName") or body.get("name") or "Marca").strip() or "Marca"
    dado_id = str(body.get("brandId") or body.get("id") or "").strip()
    # Sem `brandId` explicito e uma CRIACAO — ai o slug sai do nome e nao pode
    # cair em cima de outra marca. Com `brandId` e atualizacao daquela marca.
    bid = _slug(dado_id) if dado_id else _slug_livre(_slug(name), name)
    data = dict(body)
    data.pop("activate", None)
    data.pop("action", None)
    data["brandId"] = bid
    data["brandName"] = name
    if not data.get("exportPreset"):
        data["exportPreset"] = "reels"
    path = BRANDS_DIR / f"{bid}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def set_export_preset(fmt: str) -> dict[str, Any]:
    """Troca SO o formato de saida da marca ativa.

    `save_brand` grava `dict(body)` — o corpo do pedido vira o arquivo
    inteiro. A tela de Presets (4.19) so quer mexer no formato, e mandar
    `{exportPreset}` por ali apagaria o estilo base, o texto do cartao
    final e a cor de destaque de uma vez.
    """
    valido = ("reels", "youtube", "square", "feed")
    v = str(fmt or "").strip().lower()
    if v not in valido:
        raise ValueError("formato desconhecido")
    ensure_brands_dir()
    bid = get_active_id()
    path = BRANDS_DIR / f"{_slug(bid)}.json"
    data = load_brand(bid)
    data["exportPreset"] = v
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return data


def write_user_preset(data: dict[str, Any]) -> None:
    """Espelha o estilo ativo onde o pipeline/UI leem (pasta do usuário)."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["fastMode"] = True
    USER_PRESET.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Melhor esforço: também no pacote (dev / se tiver permissão)
    try:
        out = PREVIEW / "default-style.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def activate_brand(brand_id: str) -> dict[str, Any]:
    ensure_brands_dir()
    bid = _slug(brand_id)
    path = BRANDS_DIR / f"{bid}.json"
    if not path.exists():
        raise ValueError("marca não encontrada")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    ACTIVE_PATH.write_text(json.dumps({"activeId": bid}, indent=2) + "\n", encoding="utf-8")
    write_user_preset(data)
    return {
        "ok": True,
        "activeId": bid,
        "brand": {"id": bid, "name": data.get("brandName") or bid},
    }


def export_preset_info(preset_id: str | None) -> dict[str, Any]:
    pid = (preset_id or "reels").lower().strip()
    return dict(EXPORT_PRESETS.get(pid) or EXPORT_PRESETS["reels"])


def list_export_presets() -> list[dict[str, Any]]:
    return [dict(v) for v in EXPORT_PRESETS.values()]
