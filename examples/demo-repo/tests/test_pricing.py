import pytest

from pulse.pricing import discount_for, quote


def test_quote_applies_vat():
    total = quote([{"price": 10.0, "qty": 2}], "EU")
    assert total == pytest.approx(24.2)


def test_quote_rejects_unknown_region():
    with pytest.raises(ValueError):
        quote([{"price": 1.0, "qty": 1}], "XX")


def test_gold_discount():
    assert discount_for({"tier": "gold"}) == 0.10

# revision 72: Aiko Tanaka

# revision 73: Sam Okafor

# revision 74: Mira Chen

# revision 75: Tomas Oliveira

# revision 76: Priya Raman

# revision 77: Jonas Weber

# revision 78: Aiko Tanaka
