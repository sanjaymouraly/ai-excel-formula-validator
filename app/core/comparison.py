import math
from datetime import date, datetime, time
from numbers import Real

from openpyxl.utils.datetime import to_excel


def normalized(value):
    if isinstance(value, (datetime, date, time)):
        return to_excel(value)
    return value


def equal(actual, expected, atol=1e-8, rtol=1e-7):
    # bool is a subclass of int: compare it before numeric normalization.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if actual is None or expected is None:
        return actual is expected
    actual, expected = normalized(actual), normalized(expected)
    if isinstance(actual, Real) and isinstance(expected, Real):
        return (
            math.isfinite(actual)
            and math.isfinite(expected)
            and math.isclose(actual, expected, abs_tol=atol, rel_tol=rtol)
        )
    return type(actual) is type(expected) and actual == expected
