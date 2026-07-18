import json

from api_quality_agent.domain.models import DiffCategory, DiffChangeType, DiffRiskLevel
from api_quality_agent.domain.services import DiffEngine
from api_quality_agent.parsers import PostmanCollectionParser


def _parse(items=None, variables=None):
    document = {
        "info": {
            "name": "Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items or [],
    }
    if variables is not None:
        document["variable"] = variables
    return PostmanCollectionParser().parse_text(json.dumps(document))


def _request(name, item_id, *, url="https://x/y", events=None):
    request = {"name": name, "id": item_id, "request": {"method": "GET", "url": url}}
    if events is not None:
        request["event"] = events
    return request


def _test_event(exec_lines):
    return {"listen": "test", "script": {"exec": exec_lines}}


# --- Sem diferenças ---------------------------------------------------------------


def test_no_differences_produces_empty_diff():
    original = _parse(items=[_request("Ping", "req-1")], variables=[{"key": "a", "value": "1"}])
    modified = _parse(items=[_request("Ping", "req-1")], variables=[{"key": "a", "value": "1"}])

    diff = DiffEngine().compare(original, modified)

    assert diff.entries == ()
    assert diff.has_changes is False
    assert diff.has_removals is False
    assert diff.has_high_risk_changes is False


# --- Adição ------------------------------------------------------------------------


def test_added_variable_is_detected_as_low_risk():
    original = _parse(items=[_request("Ping", "req-1")], variables=[])
    modified = _parse(
        items=[_request("Ping", "req-1")], variables=[{"key": "token", "value": "abc123456789"}]
    )

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    entry = diff.entries[0]
    assert entry.change_type == DiffChangeType.ADDED
    assert entry.category == DiffCategory.VARIABLE
    assert entry.risk == DiffRiskLevel.LOW


def test_added_request_is_detected():
    original = _parse(items=[_request("Ping", "req-1")])
    modified = _parse(items=[_request("Ping", "req-1"), _request("Novo", "req-2")])

    diff = DiffEngine().compare(original, modified)

    added = [e for e in diff.entries if e.change_type == DiffChangeType.ADDED]
    assert len(added) == 1
    assert added[0].category == DiffCategory.REQUEST
    assert "Novo" in added[0].description


def test_added_managed_block_is_detected():
    original = _parse(items=[_request("Ping", "req-1", events=[_test_event(["// manual"])])])
    modified = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            "// manual",
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('a', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )

    diff = DiffEngine().compare(original, modified)

    block_entries = [e for e in diff.entries if e.category == DiffCategory.MANAGED_BLOCK]
    assert len(block_entries) == 1
    assert block_entries[0].change_type == DiffChangeType.ADDED
    assert block_entries[0].risk == DiffRiskLevel.LOW


# --- Modificação ---------------------------------------------------------------------


def test_modified_managed_block_content_is_detected():
    original = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('antigo', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )
    modified = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('novo', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    entry = diff.entries[0]
    assert entry.change_type == DiffChangeType.MODIFIED
    assert entry.category == DiffCategory.MANAGED_BLOCK
    assert entry.risk == DiffRiskLevel.MEDIUM
    assert "pm.test" not in entry.description


def test_manual_code_outside_block_change_is_reported_as_script_modification():
    original = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            "// comentário manual antigo",
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('a', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )
    modified = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            "// comentário manual novo",
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('a', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    assert diff.entries[0].category == DiffCategory.SCRIPT
    assert diff.entries[0].change_type == DiffChangeType.MODIFIED


def test_modified_variable_value_is_detected():
    original = _parse(items=[], variables=[{"key": "baseUrl", "value": "https://old.exemplo.com"}])
    modified = _parse(items=[], variables=[{"key": "baseUrl", "value": "https://new.exemplo.com"}])

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    assert diff.entries[0].change_type == DiffChangeType.MODIFIED
    assert diff.entries[0].category == DiffCategory.VARIABLE
    assert diff.entries[0].risk == DiffRiskLevel.MEDIUM


# --- Remoção -------------------------------------------------------------------------


def test_removed_request_is_high_risk():
    original = _parse(items=[_request("Ping", "req-1"), _request("Delete", "req-2")])
    modified = _parse(items=[_request("Ping", "req-1")])

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    entry = diff.entries[0]
    assert entry.change_type == DiffChangeType.REMOVED
    assert entry.category == DiffCategory.REQUEST
    assert entry.risk == DiffRiskLevel.HIGH
    assert diff.has_removals is True
    assert diff.has_high_risk_changes is True


def test_removed_variable_is_high_risk():
    original = _parse(items=[], variables=[{"key": "legacyVar", "value": "x"}])
    modified = _parse(items=[], variables=[])

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    assert diff.entries[0].change_type == DiffChangeType.REMOVED
    assert diff.entries[0].risk == DiffRiskLevel.HIGH


def test_removed_script_is_high_risk():
    original = _parse(
        items=[_request("Ping", "req-1", events=[_test_event(["pm.test('a', function(){});"])])]
    )
    modified = _parse(items=[_request("Ping", "req-1")])

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    assert diff.entries[0].category == DiffCategory.SCRIPT
    assert diff.entries[0].change_type == DiffChangeType.REMOVED
    assert diff.entries[0].risk == DiffRiskLevel.HIGH


def test_removed_managed_block_is_high_risk():
    original = _parse(
        items=[
            _request(
                "Ping",
                "req-1",
                events=[
                    _test_event(
                        [
                            '// <api-quality-agent:block id="auto-tests">',
                            "pm.test('a', function () {});",
                            "// </api-quality-agent:block>",
                        ]
                    )
                ],
            )
        ]
    )
    modified = _parse(
        items=[_request("Ping", "req-1", events=[_test_event(["// sem bloco gerenciado"])])]
    )

    diff = DiffEngine().compare(original, modified)

    block_entries = [e for e in diff.entries if e.category == DiffCategory.MANAGED_BLOCK]
    assert len(block_entries) == 1
    assert block_entries[0].change_type == DiffChangeType.REMOVED
    assert block_entries[0].risk == DiffRiskLevel.HIGH


# --- Mascaramento ----------------------------------------------------------------------


def test_variable_value_is_masked_never_exposed_in_plain_text():
    secret_value = "super-secret-token-value-123456"
    original = _parse(items=[], variables=[{"key": "token", "value": "old"}])
    modified = _parse(items=[], variables=[{"key": "token", "value": secret_value}])

    diff = DiffEngine().compare(original, modified)

    assert len(diff.entries) == 1
    assert secret_value not in diff.entries[0].description


def test_added_variable_value_is_masked():
    secret_value = "another-sensitive-value-xyz"
    original = _parse(items=[], variables=[])
    modified = _parse(items=[], variables=[{"key": "apiKey", "value": secret_value}])

    diff = DiffEngine().compare(original, modified)

    assert secret_value not in diff.entries[0].description
