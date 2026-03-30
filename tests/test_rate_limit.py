import os
import tempfile
import unittest

from nexora_node_sdk.auth import _rate_limit as rl


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        # Ensure clean global state and use a temp runtime file
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.runtime_path = self.tmp.name
        self.tmp.close()
        os.environ["NEXORA_AUTH_RUNTIME_FILE"] = self.runtime_path
        rl._AUTH_FAILURES.clear()
        rl._AUTH_FAILURES_SCOPE = ""

    def tearDown(self):
        try:
            os.remove(self.runtime_path)
        except OSError:
            pass
        os.environ.pop("NEXORA_AUTH_RUNTIME_FILE", None)

    def test_record_and_check_rate_limit(self):
        # Temporarily lower the threshold for faster test
        original = rl._MAX_AUTH_FAILURES
        rl._MAX_AUTH_FAILURES = 3
        try:
            ip = "10.0.0.1"
            for _ in range(3):
                rl._record_auth_failure(ip)
            self.assertTrue(rl._check_rate_limit(ip))
        finally:
            rl._MAX_AUTH_FAILURES = original


if __name__ == "__main__":
    unittest.main()
