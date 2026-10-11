from overlap import overlap_days


def test_full_overlap():
    assert overlap_days(1, 10, 5, 15) == 6   # days 5..10 inclusive = 6


def test_touching_at_one_day():
    assert overlap_days(1, 5, 5, 9) == 1      # only day 5 is shared


def test_disjoint_is_zero():
    assert overlap_days(1, 5, 10, 15) == 0
