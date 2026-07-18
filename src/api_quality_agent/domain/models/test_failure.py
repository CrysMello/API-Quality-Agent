from dataclasses import dataclass


@dataclass(frozen=True)
class TestFailure:
    request_name: str | None
    test_name: str
    error_message: str
