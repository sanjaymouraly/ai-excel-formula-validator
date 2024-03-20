from hypothesis import given
from hypothesis import strategies as st

from app.benchmarks.library import LIBRARY, generate
from app.core.comparison import equal


@given(st.integers(min_value=0, max_value=2**31 - 1), st.integers(min_value=0, max_value=100))
def test_deterministic_generators(seed, case):
    for key in LIBRARY:
        first, second = generate(key, seed, case), generate(key, seed, case)
        assert first.cells == second.cells
        assert first.expected == second.expected


@given(st.lists(st.integers(-100000, 100000), min_size=1, max_size=50))
def test_sales_oracle_sum_invariants(values):
    assert sum(values) == sum(values[::-1])
    assert sum(values + [0]) == sum(values)
    assert sum(values + [-sum(values)]) == 0


@given(st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False))
def test_numeric_comparison_reflexive(value):
    assert equal(value, value)
    assert not equal(value, None)
