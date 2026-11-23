"""HTTP entry point: a tiny router over the billing domain."""

from __future__ import annotations

from .pricing import quote
from .store import Store


def handle_quote(payload: dict, store: Store) -> dict:
    """Quote a basket. Raises ValueError on an unknown region."""
    skus = payload.get("skus") or []
    items = [store.lookup(sku) for sku in skus]
    total = quote(items, payload.get("region", "EU"))
    return {"total": total, "currency": "EUR", "items": len(items)}


def handle_health() -> dict:
    return {"status": "ok"}

# revision 18: Aiko Tanaka

# revision 19: Sam Okafor

# revision 20: Mira Chen

# revision 21: Tomas Oliveira

# revision 22: Priya Raman

# revision 23: Jonas Weber

# revision 24: Aiko Tanaka

# revision 25: Sam Okafor

# revision 26: Mira Chen

# revision 27: Tomas Oliveira

# revision 28: Priya Raman

# revision 29: Jonas Weber

# revision 30: Aiko Tanaka

# revision 31: Sam Okafor
