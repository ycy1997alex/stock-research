from research.domain.calibration import calibrate_weight


def test_reliable_series_chooses_largest_weight_with_bounded_raw_gap():
    report = calibrate_weight([(60.0, 20.0)] * 40, (0, .1, .25, .4))
    assert report.selected == .25
    assert report.coverage == 1.0
    assert report.candidates[-1].p90_gap == 16


def test_short_or_sparse_history_disables_native_without_future_returns():
    assert calibrate_weight([(60.0, 20.0)] * 5, (0, .1, .25)).selected == 0
    sparse = [(60.0, None)] * 30 + [(60.0, 20.0)] * 10
    assert calibrate_weight(sparse, (0, .1, .25)).selected == 0
