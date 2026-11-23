"""Monthly aggregation helpers used by the finance export."""

from __future__ import annotations

from collections import defaultdict


def monthly_totals(rows: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        month = row["date"][:7]
        totals[month] += row["amount"]
    return dict(sorted(totals.items()))


def top_customers(rows: list[dict], limit: int = 5) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row["customer"]] += row["amount"]
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:limit]

# revision 56: Mira Chen

# revision 57: Tomas Oliveira

# revision 58: Priya Raman

# revision 59: Jonas Weber

# revision 60: Aiko Tanaka

# revision 61: Sam Okafor

# revision 62: Mira Chen
