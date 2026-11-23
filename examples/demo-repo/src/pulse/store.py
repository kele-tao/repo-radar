"""In-memory catalogue with a deliberately naive loader."""

from __future__ import annotations


class Store:
    """Holds the catalogue. Swapped for a database client in production."""

    def __init__(self, catalogue: list[dict] | None = None) -> None:
        self.catalogue = {item["sku"]: item for item in (catalogue or [])}

    def lookup(self, sku: str) -> dict:
        return self.catalogue[sku]

    def add(self, sku: str, price: float, qty: int = 1) -> None:
        self.catalogue[sku] = {"sku": sku, "price": price, "qty": qty}

# revision 63: Tomas Oliveira

# revision 64: Priya Raman

# revision 65: Jonas Weber

# revision 66: Aiko Tanaka

# revision 67: Sam Okafor

# revision 68: Mira Chen

# revision 69: Tomas Oliveira

# revision 70: Priya Raman

# revision 71: Jonas Weber
