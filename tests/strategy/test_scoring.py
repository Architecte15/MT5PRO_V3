from app.strategy.scoring import compute_score


def test_score_detail():
    s = compute_score(htf_trend=True, breakout=True, retest=False)
    assert s.total == 2
    assert any(x.name == "retest" and not x.present for x in s.missing)
