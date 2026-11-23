"""Pricing rules. This module is intentionally the most volatile one."""

from __future__ import annotations

REGION_VAT = {"EU": 0.21, "US": 0.0, "BR": 0.17}
BULK_THRESHOLD = 10


def quote(items: list[dict], region: str = "EU") -> float:
    """Total price for a basket, VAT included."""
    subtotal = sum(item["price"] * item["qty"] for item in items)
    if len(items) >= BULK_THRESHOLD:
        subtotal *= 0.95
    rate = REGION_VAT.get(region)
    if rate is None:
        raise ValueError("unknown region: " + region)
    return round(subtotal * (1 + rate), 2)


def discount_for(customer: dict) -> float:
    tier = customer.get("tier", "basic")
    if tier == "gold":
        return 0.10
    if tier == "silver":
        return 0.05
    return 0.0

# revision 34: Priya Raman

# revision 35: Jonas Weber

# revision 36: Aiko Tanaka

# revision 37: Sam Okafor

# revision 38: Mira Chen

# revision 39: Tomas Oliveira

# revision 40: Priya Raman

# revision 41: Jonas Weber

# revision 42: Aiko Tanaka

# revision 43: Sam Okafor

# revision 44: Mira Chen

# revision 45: Tomas Oliveira

# revision 46: Priya Raman

# revision 47: Jonas Weber

# revision 48: Aiko Tanaka

# revision 49: Sam Okafor

# revision 50: Mira Chen

# revision 51: Tomas Oliveira

# revision 52: Priya Raman

# revision 53: Jonas Weber

# revision 54: Aiko Tanaka

# revision 55: Sam Okafor
