from app.models import InterestModel, ItemFormat, UnderstandResult
from app.pipeline import curate


def u(q=7, topics=("cycling",), fmt="tutorial"):
    return UnderstandResult(
        summary="s", topics=list(topics), format=ItemFormat(fmt), category="Other",
        intrinsic_quality=q, reason="r",
    )


def test_cold_start_ranks_by_quality_only():
    good = curate.build_card("a", u(q=8.5))
    bait = curate.build_card("b", u(q=1.5, topics=("deals",), fmt="promo"))
    assert good.value_score == 8.5 and good.tier == "highlight"
    assert bait.value_score == 1.5 and bait.tier == "skipped"
    assert good.score_breakdown["confidence"] == 0


def test_interest_fit_moves_scores_both_ways():
    m = InterestModel(topic_weights={"cycling": 1.0, "memes": -1.0, "x": 1.0}, version=3)
    liked = curate.build_card("a", u(q=6, topics=("cycling",)), m)
    disliked = curate.build_card("b", u(q=6, topics=("memes",), fmt="humor"), m)
    neutral = curate.build_card("c", u(q=6, topics=("gardening",)), m)
    assert liked.value_score > neutral.value_score > disliked.value_score
    assert liked.fit_note == "Matches your interest in cycling"
    assert disliked.fit_note == "You tend to skip memes"


def test_focus_hint_bootstraps_without_behavior():
    m = InterestModel(focus_hint=["ai"])
    on = curate.build_card("a", u(q=6, topics=("ai", "llms")), m)
    off = curate.build_card("b", u(q=6, topics=("travel",)), m)
    assert on.value_score > off.value_score
    assert 0 < on.score_breakdown["confidence"] < 1


def test_novelty_penalizes_near_duplicates():
    recent = [["cooking", "pasta"], ["cooking", "pasta"], ["cooking"]]
    fresh = curate.build_card("a", u(q=7, topics=("cooking", "pasta")), recent_topics=[])
    repeat = curate.build_card("b", u(q=7, topics=("cooking", "pasta")), recent_topics=recent)
    assert repeat.value_score < fresh.value_score
    assert repeat.score_breakdown["novelty_penalty"] > 0


def test_rescore_updates_tier_and_keeps_novelty():
    card = curate.build_card("a", u(q=6, topics=("cycling",)))
    assert card.tier == "normal"
    m = InterestModel(topic_weights={"cycling": 1.5}, format_weights={"tutorial": 1.0})
    again = curate.rescore(card, m)
    assert again.tier == "highlight" and again.value_score > card.value_score
    m2 = InterestModel(topic_weights={"cycling": -1.5}, format_weights={"tutorial": -1.0})
    assert curate.rescore(card, m2).tier == "skipped"


def test_scores_are_clamped():
    m = InterestModel(topic_weights={"cycling": 9.0}, format_weights={"tutorial": 9.0})
    assert curate.build_card("a", u(q=10), m).value_score <= 10
    assert curate.build_card("b", u(q=0, topics=("x",) * 1), InterestModel()).value_score >= 0
