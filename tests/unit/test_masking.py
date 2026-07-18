import pytest

from api_quality_agent.shared import mask_secret


def test_masks_long_value_matching_sad_example():
    assert mask_secret("P0STM4N-API-KEY-EXEMPLO-123456") == "P0ST" + "*" * 22 + "3456"


def test_masks_short_value_completely():
    assert mask_secret("abcd") == "****"


def test_masks_value_exactly_at_boundary_completely():
    assert mask_secret("abcdefgh") == "*" * 8


def test_masks_empty_string_as_empty():
    assert mask_secret("") == ""


def test_masked_value_has_same_length_as_original():
    original = "some-secret-value-1234567890"
    masked = mask_secret(original)
    assert len(masked) == len(original)


def test_masked_value_never_exposes_middle_characters():
    original = "abcdefghijklmnopqrstuvwxyz"
    masked = mask_secret(original)
    middle = original[4:-4]
    assert middle not in masked


def test_rejects_non_string_value():
    with pytest.raises(TypeError):
        mask_secret(12345)
