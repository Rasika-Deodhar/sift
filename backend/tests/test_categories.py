from app.categories import group_lanes, suggest_other_name
from app.models import ItemCard, ItemFormat

from .conftest import FakeClient


def card(i, cat, score=5):
    return ItemCard(item_id=str(i), summary=f"s{i}", topics=["t"], category=cat,
                    format=ItemFormat.other, value_score=score, reason="r")


def test_group_lanes_sorted_and_complete():
    lanes = group_lanes([card(1, "Humor", 3), card(2, "Humor", 8), card(3, "Other")])
    assert list(lanes)[0] == "Tutorials & How-to"
    assert [c.item_id for c in lanes["Humor"]] == ["2", "1"]
    assert len(lanes["Other"]) == 1


async def test_other_lane_name_only_when_large():
    few = [card(i, "Other") for i in range(2)]
    assert await suggest_other_name(FakeClient(default={"name": "Pets"}), few) is None
    many = [card(i, "Other") for i in range(5)]
    assert await suggest_other_name(FakeClient(default={"name": "Pets"}), many) == "Pets"
    assert await suggest_other_name(FakeClient(default={"name": ""}), many) is None
