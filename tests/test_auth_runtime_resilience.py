from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nexora_core.auth as auth


class AuthRuntimeResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_api_token = auth._token._api_token

    def tearDown(self) -> None:
        auth._token._api_token = self._original_api_token
        auth._AUTH_FAILURES.clear()

    def test_rate_limit_state_persists_across_memory_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "auth-runtime.json"
            with patch.dict(
                os.environ,
                {"NEXORA_AUTH_RUNTIME_FILE": str(runtime_path)},
                clear=False,
            ):
                auth._AUTH_FAILURES.clear()
                ip = "198.51.100.42"
                for _ in range(auth._MAX_AUTH_FAILURES):
                    auth._record_auth_failure(ip)

                auth._AUTH_FAILURES.clear()
                self.assertTrue(auth._check_rate_limit(ip))
                self.assertTrue(runtime_path.exists())


if __name__ == "__main__":
    unittest.main()