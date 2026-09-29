from app.risk.position_sizer import SymbolSpec, calculate_volume


def test_volume_zero_when_minimum_would_exceed_risk():
    spec = SymbolSpec(0.00001, 0.00001, 1.0, 100000, 1.0, 100.0, 1.0)
    vol = calculate_volume(1000, 1.0, 1.1000, 1.0998, spec)
    assert vol == 0.0
