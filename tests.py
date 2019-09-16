import pytest

from summary import to_seconds, nice_date


@pytest.mark.parametrize(['input', 'expected'], [
    ('30', 30),
    ('30s', 30),
    ('30 sec', 30),
    ('30 seconds', 30),
    ('1 second', 1),
    ('5m', 5 * 60),
    ('5 min', 5 * 60),
    ('5 minutes', 5 * 60),
    ('1 minute', 60),
    ('2h', 2 * 60 * 60),
    ('2 hours', 2 * 60 * 60),
    ('1 hour', 60 * 60),
])
def test_to_seconds(input, expected):
    assert to_seconds(input) == expected


def test_nice_date():
    nice_date("2019-06-06 17:43:14 +0300")  # should not raise
