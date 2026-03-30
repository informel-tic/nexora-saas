import tempfile
import unittest

from nexora_node_sdk import secret_store


class SecretStoreTests(unittest.TestCase):
    def test_issue_and_verify_and_read(self):
        with tempfile.TemporaryDirectory() as td:
            meta = secret_store.issue_secret(td, owner_type="node", owner_id="node1", scopes=["a"])
            self.assertEqual(meta["owner_type"], "node")
            token = secret_store.read_secret(td, owner_type="node", owner_id="node1")
            self.assertIsNotNone(token)
            self.assertTrue(secret_store.verify_secret(td, owner_type="node", owner_id="node1", provided_token=token))
            self.assertFalse(secret_store.verify_secret(td, owner_type="node", owner_id="node1", provided_token="wrong"))

    def test_revoke_secret(self):
        with tempfile.TemporaryDirectory() as td:
            secret_store.issue_secret(td, owner_type="service", owner_id="svc1")
            self.assertIsNotNone(secret_store.read_secret(td, owner_type="service", owner_id="svc1"))
            secret_store.revoke_secret(td, owner_type="service", owner_id="svc1")
            # After revoke, read_secret should return None
            self.assertIsNone(secret_store.read_secret(td, owner_type="service", owner_id="svc1"))

    def test_list_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            secret_store.issue_secret(td, owner_type="node", owner_id="n1")
            secret_store.issue_secret(td, owner_type="operator", owner_id="op1")
            all_secrets = secret_store.list_secrets(td)
            self.assertTrue(any(s["owner_id"] == "n1" for s in all_secrets))
            self.assertTrue(any(s["owner_id"] == "op1" for s in all_secrets))

    def test_invalid_owner_type(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                secret_store.issue_secret(td, owner_type="invalid", owner_id="x")


if __name__ == "__main__":
    unittest.main()
