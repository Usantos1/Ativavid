"""B-roll automático (Pexels) para o pipeline 1-clique.

Gera inserts em edit-data a partir da fala. Falha de forma silenciosa
(sem chave / sem rede) — o render segue sem imagens.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Stopwords PT curtas — evitam queries inúteis
_STOP = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos",
    "e", "é", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "que",
    "se", "eu", "você", "voce", "ele", "ela", "nós", "nos", "já", "ja", "não", "nao",
    "mais", "muito", "pouco", "aqui", "ali", "isso", "isto", "esse", "essa", "este",
    "esta", "então", "entao", "porque", "quando", "como", "também", "tambem", "só",
    "so", "vai", "vou", "tem", "ter", "foi", "ser", "são", "sao", "pra", "pro",
}


def _pexels_key() -> str | None:
    # ORDEM DO APP: `%USERPROFILE%/ATIVAVID/.env` primeiro. Numa
    # instalacao normal o codigo fica em Program Files (so leitura) e a
    # tela de Integracoes grava no do usuario; o .env ao lado do codigo
    # so existe na maquina de quem desenvolve. Sem esta linha o helper
    # depende de o app injetar a chave no ambiente, e quando isso falha
    # o sintoma e MUDO (a 3.26 consertou o mesmo no Groq).
    for candidate in [Path.home() / "ATIVAVID" / ".env",
                      Path(__file__).resolve().parent.parent / ".env",
                      Path(".env")]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == "PEXELS_API_KEY":
                        val = v.strip().strip('"').strip("'")
                        if val:
                            return val
            except OSError:
                pass
    return os.environ.get("PEXELS_API_KEY") or None


def keywords_from_text(text: str, limit: int = 4) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", text or "", flags=re.UNICODE)
    scored: dict[str, int] = {}
    for w in words:
        low = w.lower()
        if low in _STOP:
            continue
        scored[low] = scored.get(low, 0) + 1
    ranked = sorted(scored.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    out: list[str] = []
    for w, _ in ranked:
        if w not in out:
            out.append(w)
        if len(out) >= limit:
            break
    return out


def _mode_count(mode: str) -> int:
    m = (mode or "quando_necessario").lower().strip()
    if m in ("off", "nenhum", "none", "desligado"):
        return 0
    if m in ("sempre", "always", "frequente"):
        return 3
    if m in ("raro", "pouco"):
        return 1
    return 2  # quando_necessario


def build_auto_inserts(
    *,
    public_dir: Path,
    transcript: str,
    duration: float,
    mode: str = "quando_necessario",
    hook_end: float = 3.0,
    end_card_sec: float = 2.5,
) -> list[dict[str, Any]]:
    """Baixa imagens e devolve lista no formato edit-data inserts[]."""
    n = _mode_count(mode)
    if n <= 0 or duration < 6:
        return []
    key = _pexels_key()
    if not key:
        print("[broll] PEXELS_API_KEY ausente — sem inserts auto", flush=True)
        return []

    try:
        import pexels_search  # type: ignore
    except ImportError:
        print("[broll] pexels_search indisponível", flush=True)
        return []

    kws = keywords_from_text(transcript, limit=max(2, n))
    if not kws:
        kws = ["produto", "loja"]

    usable = max(0.0, duration - hook_end - end_card_sec - 0.4)
    if usable < 1.2:
        return []

    slot = usable / n
    inserts: list[dict[str, Any]] = []
    out_dir = public_dir / "pexels"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        query = " ".join(kws[i : i + 2]) if i < len(kws) else kws[0]
        try:
            photos = pexels_search.search(query, key, 3, "portrait")
        except Exception as e:  # noqa: BLE001
            print(f"[broll] busca falhou ({query}): {e}", flush=True)
            continue
        if not photos:
            continue
        photo = photos[0]
        src = photo.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        name = f"{pexels_search.slugify(query)}-auto{i + 1}.jpg"
        dest = out_dir / name
        try:
            pexels_search.download(url, dest)
        except Exception as e:  # noqa: BLE001
            print(f"[broll] download falhou: {e}", flush=True)
            continue
        start = hook_end + 0.3 + i * slot
        end = min(duration - end_card_sec - 0.2, start + min(1.6, max(1.0, slot * 0.55)))
        if end <= start + 0.6:
            continue
        inserts.append({
            "src": f"pexels/{name}",
            "start": round(start, 3),
            "end": round(end, 3),
            "credit": photo.get("photographer") or "",
            "auto": True,
        })
        print(f"[broll] + {name} @ {start:.1f}-{end:.1f}s ({query})", flush=True)

    return inserts
