"""User-provided validators for GoldenCase entries with assert_type: custom.

Referenced from golden/*.yaml as "tests.golden.custom_assertions:<name>".
A validator receives (actual, expected) and should raise AssertionError on
failure -- a plain assert statement is enough.
"""


def assert_positive_word_count(actual: int, expected: object) -> None:
    assert actual > 0, f"expected a positive word count, got {actual}"
