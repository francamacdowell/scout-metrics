from scout.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_INTERRUPT,
    EXIT_IO_ERROR,
    EXIT_OK,
    EXIT_PARSE_ERROR,
    EXIT_VIOLATIONS,
    ConfigError,
    DiscoveryError,
    ScoutError,
    ScoutIOError,
)


def test_exit_code_values():
    assert EXIT_OK == 0
    assert EXIT_VIOLATIONS == 1
    assert EXIT_CONFIG_ERROR == 2
    assert EXIT_IO_ERROR == 3
    assert EXIT_PARSE_ERROR == 4
    assert EXIT_INTERRUPT == 130


def test_exception_hierarchy():
    assert issubclass(ConfigError, ScoutError)
    assert issubclass(ScoutIOError, ScoutError)
    assert issubclass(DiscoveryError, ScoutError)


def test_config_error_message():
    e = ConfigError("bad flag")
    assert "bad flag" in str(e)


def test_scout_error_is_exception():
    try:
        raise ScoutError("boom")
    except Exception as exc:
        assert str(exc) == "boom"
