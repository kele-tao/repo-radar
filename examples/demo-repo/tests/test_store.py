import pytest

from pulse.store import Store


def test_lookup_roundtrip():
    store = Store()
    store.add("abc", 3.5)
    assert store.lookup("abc")["price"] == 3.5


def test_unknown_sku_raises():
    store = Store()
    with pytest.raises(KeyError):
        store.lookup("nope")

# revision 79: Sam Okafor

# revision 80: Mira Chen

# revision 81: Tomas Oliveira

# revision 82: Priya Raman
