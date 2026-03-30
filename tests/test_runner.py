import asyncio
import sys
import tempfile
from types import SimpleNamespace

from yunohost_mcp.utils import runner


def test_format_result_success():
    r = runner.YnhResult(success=True, data={"x": 1})
    out = runner.format_result(r)
    assert "\"x\"" in out or "x" in out


def test_run_shell_command_safe_python():
    orig_audit = runner._audit
    orig_load = runner.load_settings
    runner._audit = lambda *a, **k: None
    try:
        with tempfile.TemporaryDirectory() as td:
            runner.load_settings = lambda: SimpleNamespace(allow_destructive_tools=False, audit_log_path=str(td + "/audit.log"))
            res = asyncio.run(runner.run_shell_command_safe([sys.executable, "-c", "print('ok-run')"]))
            assert "ok-run" in res
    finally:
        runner.load_settings = orig_load
        runner._audit = orig_audit


def test_run_ynh_command_not_found():
    orig_audit = runner._audit
    orig_load = runner.load_settings
    runner._audit = lambda *a, **k: None
    runner.load_settings = lambda: SimpleNamespace(allow_destructive_tools=False, audit_log_path="/dev/null")
    try:
        result = asyncio.run(runner.run_ynh_command("version"))
        assert result.success is False
        assert (result.error and "introuvable" in result.error) or (result.raw_output and "introuvable" in result.raw_output)
    finally:
        runner.load_settings = orig_load
        runner._audit = orig_audit
