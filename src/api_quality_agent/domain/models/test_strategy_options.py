from dataclasses import dataclass


@dataclass(frozen=True)
class TestStrategyOptions:
    expected_status_code: int | None = None
    max_response_time_ms: int | None = None
    assert_array_not_empty: bool = False
    assert_no_extra_properties: bool = False
    assert_required_has_value: bool = False
    enable_snapshot: bool = False
