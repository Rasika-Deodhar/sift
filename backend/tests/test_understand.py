import pytest

from app.models import InterestModel
from app.pipeline.understand import UnderstandError, describe_interests, understand

from .conftest import TINY_JPEG, FakeClient, good_result


async def test_valid_output_is_normalized():
    u = await understand(FakeClient([good_result(category="tutorials & how-to")]), [TINY_JPEG])
    assert u.topics == ["cycling", "bike maintenance"]
    assert u.category == "Tutorials & How-to"


async def test_unknown_category_maps_to_other():
    u = await understand(FakeClient([good_result(category="Cats")]), [TINY_JPEG])
    assert u.category == "Other"


async def test_retries_once_on_invalid_json_then_succeeds():
    bad = good_result(intrinsic_quality=42)  # out of range
    client = FakeClient([bad, good_result()])
    u = await understand(client, [TINY_JPEG])
    assert u.intrinsic_quality == 8
    assert len(client.calls) == 2
    assert "previous answer was invalid" in client.calls[1]["prompt"]


async def test_retries_on_parse_error():
    client = FakeClient([ValueError("no JSON object in model output"), good_result()])
    assert (await understand(client, [TINY_JPEG])).format == "tutorial"


async def test_gives_up_after_one_retry():
    client = FakeClient([{"summary": ""}, {"topics": []}])
    with pytest.raises(UnderstandError):
        await understand(client, [TINY_JPEG])
    assert len(client.calls) == 2


async def test_prompt_includes_interest_profile():
    client = FakeClient()
    m = InterestModel(topic_weights={"cycling": 0.8, "memes": -0.5}, focus_hint=["ai"])
    await understand(client, [TINY_JPEG], m)
    p = client.calls[0]["prompt"]
    assert "cycling (+0.80)" in p and "memes (-0.50)" in p and "ai" in p


def test_describe_interests_cold_start():
    assert "cold start" in describe_interests(InterestModel())
