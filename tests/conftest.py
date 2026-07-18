import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest  # noqa: E402

from postman_test_server import PostmanTestServer  # noqa: E402


@pytest.fixture
def postman_test_server():
    server = PostmanTestServer()
    try:
        yield server
    finally:
        server.shutdown()
