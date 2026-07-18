import dataclasses

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import InputOrigin, ResolvedInput


def test_creates_valid_resolved_input():
    resolved = ResolvedInput(
        origin=InputOrigin.FILE,
        content_type="json",
        name="dados.json",
        content="{}",
    )
    assert resolved.origin == InputOrigin.FILE
    assert resolved.content_type == "json"
    assert resolved.name == "dados.json"
    assert resolved.content == "{}"


def test_rejects_empty_name():
    with pytest.raises(InputError):
        ResolvedInput(origin=InputOrigin.INLINE, content_type="json", name="", content="{}")


def test_rejects_empty_content_type():
    with pytest.raises(InputError):
        ResolvedInput(origin=InputOrigin.INLINE, content_type="", name="dados", content="{}")


def test_resolved_input_is_immutable():
    resolved = ResolvedInput(
        origin=InputOrigin.INLINE, content_type="json", name="dados", content="{}"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.content = "[]"
