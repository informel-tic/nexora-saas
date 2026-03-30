import json
import logging

from nexora_node_sdk import logging_config


def test_json_formatter_outputs_valid_json():
    formatter = logging_config.JsonFormatter()
    record = logging.LogRecord(name="tst", level=logging.INFO, pathname=__file__, lineno=1, msg="hello", args=(), exc_info=None)
    s = formatter.format(record)
    payload = json.loads(s)
    assert "timestamp" in payload and "level" in payload and payload["message"] == "hello"


def test_setup_logging_adds_handler_with_json_env(monkeypatch):
    # Ensure we start with no root handlers for the test
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    root.handlers.clear()
    monkeypatch.setenv("NEXORA_JSON_LOGS", "1")
    try:
        logger = logging_config.setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG
        # Handler should be present and use JsonFormatter
        assert any(isinstance(h.formatter, logging_config.JsonFormatter) for h in logger.handlers)
    finally:
        # restore handlers
        root.handlers[:] = old_handlers
        monkeypatch.delenv("NEXORA_JSON_LOGS", raising=False)
