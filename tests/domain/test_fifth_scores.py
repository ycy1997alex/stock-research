"""Batch-five directional, dual-axis and missing-data acceptance tests."""

import datetime as dt

import pytest

from research.domain import scoring_stock as ss


def _bars(n=300, *, step=0.2, volume=100_000):
    closes = [100 + step * i for i in range(n)]
    return dict(closes=closes, opens=[x - 0.1 for x in closes],
                highs=[x + 1 for x in closes], lows=[x - 1 for x in closes],
                volumes=[volume] * n)


def test_three_weighted_directional_terms_and_cross_market_comparable():
    bars = _bars()
    tw = ss.score_stock("2330.TW", **bars)
    us = ss.score_stock("AAPL", **bars)
    assert tw.comparable == us.comparable
    assert tw.technical == pytest.approx(.3 * tw.short.score + .4 * tw.mid.score + .3 * tw.long.score)
    assert sum(item.weight for item in tw.short.items) == pytest.approx(1)
    assert sum(item.weight for item in tw.mid.items) == pytest.approx(1)
    assert sum(item.weight for item in tw.long.items) == pytest.approx(1)
    assert -100 <= tw.comparable <= 100
    assert ss.score_stock("AAPL", **_bars(step=-.2)).comparable < tw.comparable


def test_short_history_and_thin_liquidity_do_not_manufacture_volume_scores():
    young = ss.score_stock("SPCX", **_bars(59))
    assert young.short.score is not None
    assert young.mid.score is None and young.long.score is None
    assert young.technical == pytest.approx(young.short.score)
    thin = ss.score_stock("HNHPF", **_bars())
    assert any("薄流動性" in note for note in thin.caveats)
    assert next(i for i in thin.short.items if i.name == "量價配合").score is None
    assert next(i for i in thin.mid.items if i.name == "OBV").score is None


def test_raw_gap_identity_override_last_and_missing_local():
    pair = ss.combine_scores(80, -100, .5, ss.RiskContext(blowoff=True))
    assert pair.native_raw - pair.comparable_raw == pytest.approx(.5 * (-100 - 80))
    assert pair.raw_gap == pytest.approx(-90)
    assert pair.native - pair.comparable != pytest.approx(pair.raw_gap)
    assert pair.overrides
    after = ss.combine_scores(0, 100, .5, ss.RiskContext(blowoff=True))
    assert after.native_raw == 50 and after.native == 10
    no_local = ss.combine_scores(42, None, .25)
    assert no_local.native == no_local.comparable == 42
    assert no_local.local_note == "無本地資料"
    disabled = ss.combine_scores(42, -80, 0)
    assert disabled.native == disabled.comparable


@pytest.mark.parametrize("score,text", [(80,"★★★★★"),(60,"★★★★"),(40,"★★★"),(20,"★★"),
                                          (19.99,"—"),(-19.99,"—"),(-20,"☆☆"),
                                          (-40,"☆☆☆"),(-60,"☆☆☆☆"),(-80,"☆☆☆☆☆")])
def test_star_boundaries(score, text):
    assert ss.to_stars(score)["text"] == text


def test_strength_responds_to_activity_and_is_not_a_score_weight():
    low = _bars(step=0)
    low["closes"] = [100 + (0.1 if i % 2 else -.1) for i in range(300)]
    low["opens"] = low["closes"][:]
    low["highs"] = [v + .2 for v in low["closes"]]
    low["lows"] = [v - .2 for v in low["closes"]]
    high = dict(low)
    high["volumes"] = [100_000] * 295 + [1_000_000] * 5
    quiet = ss.score_stock("AAPL", **low)
    active = ss.score_stock("AAPL", **high)
    assert quiet.strength is not None and active.strength is not None
    assert active.strength > quiet.strength
    assert abs(active.comparable - quiet.comparable) <= 20
    assert ss.combine_scores(20, 60, .25).native_raw == pytest.approx(30)
    assert ss.score_stock("AAPL", [100] * 10).strength is None


def test_flat_price_is_neutral_at_both_volume_levels_but_strength_changes():
    bars = _bars(step=0)
    quiet = ss.score_stock("AAPL", **bars)
    bars["volumes"] = [100_000] * 295 + [1_000_000] * 5
    active = ss.score_stock("AAPL", **bars)
    assert abs(quiet.comparable) <= 10
    assert abs(active.comparable) <= 10
    assert active.strength - quiet.strength >= 15


def test_us_13f_age_marks_expired_and_excludes_weight():
    from research.domain.local_stock import score_us_local
    local = score_us_local({"institutional": {"value": {"held_pct": 65},
                                             "data_date": "2026-05-01", "source": "13F"}},
                           dt.date(2026, 9, 21))
    assert local.score is None
    assert local.items[0].status == "過期"
    assert local.items[0].age_days == 143


def test_missing_high_low_or_volume_marks_dependent_indicators_missing():
    bars = _bars()
    bars["highs"][-1] = None
    bars["volumes"][-1] = None
    result = ss.score_stock("AAPL", **bars)
    assert result.comparable is not None
    assert next(i for i in result.short.items if i.name == "KD(9,3,3)").score is None
    assert next(i for i in result.short.items if i.name == "量價配合").score is None
