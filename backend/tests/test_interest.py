import pytest

from app import interest
from app.models import InterestModel, ItemCard, ItemFormat, Signal, SignalType


def card(topics=("cycling", "bike maintenance"), fmt="tutorial"):
    return ItemCard(item_id="a", summary="s", topics=list(topics), category="Other",
                    format=ItemFormat(fmt), value_score=5, reason="r")


def test_dwell_value_bands():
    assert interest.dwell_value(500) < 0
    assert interest.dwell_value(2000) == 0
    assert interest.dwell_value(3000) == pytest.approx(0.25)
    assert interest.dwell_value(15000) == pytest.approx(0.75)
    assert interest.dwell_value(60000) == pytest.approx(0.75)


def test_save_raises_topic_and_format_weights_with_position_discount():
    m0 = InterestModel(updated_at=0)
    m1, changes = interest.apply_signal(m0, card(), Signal(item_id="a", type="save", created_at=0))
    assert m1.version == 1
    assert m1.topic_weights["cycling"] == pytest.approx(0.5)
    assert m1.topic_weights["bike maintenance"] == pytest.approx(0.5 / 1.5)
    assert m1.format_weights["tutorial"] == pytest.approx(0.3)
    assert {c.key for c in changes} == {"cycling", "bike maintenance", "tutorial"}


def test_hide_lowers_weights():
    m0 = InterestModel(topic_weights={"cycling": 0.2}, updated_at=0)
    m1, _ = interest.apply_signal(m0, card(), Signal(item_id="a", type=SignalType.hide,
                                                     created_at=0))
    assert m1.topic_weights["cycling"] == pytest.approx(-0.3)


def test_exponential_decay_half_life():
    m0 = InterestModel(topic_weights={"memes": 1.0}, updated_at=0)
    s = Signal(item_id="a", type="dwell", value=2000, created_at=interest.HALF_LIFE_MS)
    m1, changes = interest.apply_signal(m0, card(), s)  # neutral dwell: decay only
    assert changes == []
    assert m1.topic_weights["memes"] == pytest.approx(0.5)


def test_weights_are_clamped_and_pruned():
    m = InterestModel(updated_at=0)
    for _ in range(10):
        m, _ = interest.apply_signal(m, card(("ai",)), Signal(item_id="a", type="save",
                                                               created_at=0))
    assert m.topic_weights["ai"] == interest.MAX_WEIGHT
    tiny = InterestModel(topic_weights={"old": 0.03}, updated_at=0)
    later = Signal(item_id="a", type="dwell", value=2000, created_at=interest.HALF_LIFE_MS)
    assert "old" not in interest.apply_signal(tiny, card(), later)[0].topic_weights


def test_diff_orders_by_magnitude():
    a = InterestModel(topic_weights={"x": 0.1, "y": 0.0})
    b = InterestModel(topic_weights={"x": 0.2, "y": -0.9}, format_weights={"humor": -0.3})
    d = interest.diff(a, b)
    assert [c["key"] for c in d] == ["y", "humor", "x"]
