"""Statistics checked against values computed by hand."""

from __future__ import annotations

import pytest

from eval_builder.judge.stats import cohen_kappa, kappa_interval, majority, wilson


def test_wilson_8_of_10() -> None:
    # p = 0.8, n = 10, z = 1.96:
    # centre = (0.8 + 1.96^2/20) / (1 + 1.96^2/10) = 0.99208 / 1.38416 = 0.71674
    # half   = 1.96 * sqrt(0.8*0.2/10 + 1.96^2/400) / 1.38416 = 0.22658
    lo, hi = wilson(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-4)
    assert hi == pytest.approx(0.9433, abs=1e-4)


def test_wilson_edges() -> None:
    lo, hi = wilson(0, 20)
    assert lo == 0.0 and hi == pytest.approx(0.1611, abs=1e-4)  # z^2/(n+z^2) = 3.8415/23.8415
    assert wilson(0, 0) is None


def test_kappa_textbook_example() -> None:
    # 50 items: both yes 20, a yes/b no 5, a no/b yes 10, both no 15
    a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    k, po, pe = cohen_kappa(a, b)
    # po = 35/50 = 0.70; pe = 0.5*0.6 + 0.5*0.4 = 0.50; kappa = 0.2/0.5 = 0.40
    assert po == pytest.approx(0.70) and pe == pytest.approx(0.50) and k == pytest.approx(0.40)
    # se = sqrt(0.7*0.3 / (50 * 0.25)) = 0.129615; 0.4 +/- 1.96*se
    lo, hi = kappa_interval(po, pe, 50)
    assert lo == pytest.approx(0.1460, abs=1e-3) and hi == pytest.approx(0.6540, abs=1e-3)


def test_kappa_perfect_and_degenerate() -> None:
    k, po, _ = cohen_kappa(["A", "B", "A"], ["A", "B", "A"])
    assert k == pytest.approx(1.0) and po == 1.0
    k, _, pe = cohen_kappa(["A", "A"], ["A", "A"])
    assert k is None and pe == 1.0
    k, _, _ = cohen_kappa(["A", "A", "A", "A"], ["A", "B", "A", "B"])  # constant judge
    assert k == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cohen_kappa(["A"], ["A", "B"])


def test_majority() -> None:
    assert majority(["A", "A", "B"]) == ("A", pytest.approx(2 / 3))
    assert majority(["A", "B"]) == (None, 0.5)
    assert majority([]) == (None, 0.0)


def test_majority_vote_stability_hypergeometric() -> None:
    from eval_builder.judge.stats import majority_vote_stability

    # 4 A, 1 B, draw 3 of 5: P(>=2 A) = [C(4,2)C(1,1) + C(4,3)C(1,0)] / C(5,3) = (6+4)/10
    assert majority_vote_stability({"A": 4, "B": 1}) == pytest.approx(1.0)
    # 3 A, 2 B: [C(3,2)C(2,1) + C(3,3)] / 10 = (6 + 1) / 10
    assert majority_vote_stability({"A": 3, "B": 2}) == pytest.approx(0.7)
    assert majority_vote_stability({"A": 5}) == pytest.approx(1.0)
    assert majority_vote_stability({"A": 2, "B": 1}) is None  # fewer than k + 2 trials
    assert majority_vote_stability({"A": 3, "B": 3}) is None  # no strict majority
