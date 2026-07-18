import api_quality_agent


def test_package_is_importable():
    assert api_quality_agent is not None


def test_package_has_version():
    assert isinstance(api_quality_agent.__version__, str)
    assert api_quality_agent.__version__
