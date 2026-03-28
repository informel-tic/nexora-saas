"""Tests for the SaaS-to-node HMAC connector."""
from __future__ import annotations

import hashlib
import hmac
import json
import unittest

from nexora_saas.node_connector import (
    NodeConnector,
    _compute_hmac_signature,
    build_cron_install_command,
    build_docker_install_command,
    build_establish_secret_command,
    build_heartbeat_command,
    build_nginx_install_command,
    build_rollback_command,
    build_service_deploy_command,
    build_systemd_install_command,
)


class HMACSignatureTests(unittest.TestCase):
    def test_signature_deterministic(self):
        sig1 = _compute_hmac_signature("secret", "test-action", "2025-01-01T00:00:00Z", {"key": "val"})
        sig2 = _compute_hmac_signature("secret", "test-action", "2025-01-01T00:00:00Z", {"key": "val"})
        self.assertEqual(sig1, sig2)

    def test_signature_changes_with_secret(self):
        sig1 = _compute_hmac_signature("secret-a", "act", "ts", None)
        sig2 = _compute_hmac_signature("secret-b", "act", "ts", None)
        self.assertNotEqual(sig1, sig2)

    def test_signature_changes_with_action(self):
        sig1 = _compute_hmac_signature("secret", "act-a", "ts", None)
        sig2 = _compute_hmac_signature("secret", "act-b", "ts", None)
        self.assertNotEqual(sig1, sig2)

    def test_signature_changes_with_timestamp(self):
        sig1 = _compute_hmac_signature("secret", "act", "ts-a", None)
        sig2 = _compute_hmac_signature("secret", "act", "ts-b", None)
        self.assertNotEqual(sig1, sig2)

    def test_signature_changes_with_payload(self):
        sig1 = _compute_hmac_signature("secret", "act", "ts", {"a": 1})
        sig2 = _compute_hmac_signature("secret", "act", "ts", {"a": 2})
        self.assertNotEqual(sig1, sig2)

    def test_signature_is_valid_hmac_sha256(self):
        secret = "test-secret-32chars-abcdefghijkl"
        action = "docker/install"
        ts = "2025-01-01T00:00:00Z"
        payload = {"name": "test"}
        sig = _compute_hmac_signature(secret, action, ts, payload)

        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        message = f"{action}:{ts}:{body}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(sig, expected)


class NodeConnectorTests(unittest.TestCase):
    def setUp(self):
        self.connector = NodeConnector(
            node_id="node-test-01",
            base_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
            api_token="test-api-token",
        )

    def test_build_command_basic(self):
        cmd = self.connector.build_command("docker/install", "/overlay/docker/install")
        self.assertEqual(cmd["node_id"], "node-test-01")
        self.assertEqual(cmd["method"], "POST")
        self.assertIn("/overlay/docker/install", cmd["url"])
        self.assertIn("X-Nexora-SaaS-Signature", cmd["headers"])
        self.assertIn("X-Nexora-SaaS-Timestamp", cmd["headers"])
        self.assertIn("Authorization", cmd["headers"])
        self.assertEqual(cmd["action"], "docker/install")

    def test_build_command_with_payload(self):
        payload = {"name": "test-service", "compose": "version: '3'"}
        cmd = self.connector.build_command("service/deploy", "/overlay/service/deploy", payload)
        self.assertEqual(cmd["body"], payload)

    def test_trailing_slash_stripped(self):
        conn = NodeConnector("n1", "http://host:38121/", "secret" * 6)
        cmd = conn.build_command("test", "/endpoint")
        self.assertEqual(cmd["url"], "http://host:38121/endpoint")


class CommandBuilderTests(unittest.TestCase):
    def setUp(self):
        self.connector = NodeConnector(
            node_id="node-01",
            base_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )

    def test_establish_secret_command(self):
        cmd = build_establish_secret_command(self.connector, "my-secret-1234567890123456789012")
        self.assertEqual(cmd["action"], "establish-secret")
        self.assertIn("/overlay/establish-secret", cmd["url"])
        self.assertEqual(cmd["body"]["saas_secret"], "my-secret-1234567890123456789012")

    def test_heartbeat_command(self):
        cmd = build_heartbeat_command(self.connector, lease_seconds=3600)
        self.assertEqual(cmd["action"], "overlay/heartbeat")
        self.assertEqual(cmd["body"]["lease_seconds"], 3600)

    def test_docker_install_command(self):
        cmd = build_docker_install_command(self.connector)
        self.assertEqual(cmd["action"], "docker/install")
        self.assertIsNone(cmd["body"])

    def test_service_deploy_command(self):
        cmd = build_service_deploy_command(
            self.connector, "my-service", "version: '3'", "location /x { }"
        )
        self.assertEqual(cmd["action"], "service/deploy")
        self.assertEqual(cmd["body"]["name"], "my-service")
        self.assertEqual(cmd["body"]["nginx_snippet"], "location /x { }")

    def test_nginx_install_command(self):
        cmd = build_nginx_install_command(self.connector, "proxy", "location /", "example.com")
        self.assertEqual(cmd["action"], "nginx/install")
        self.assertEqual(cmd["body"]["domain"], "example.com")

    def test_cron_install_command(self):
        cmd = build_cron_install_command(self.connector, "backup", "0 3 * * *", "/opt/backup.sh")
        self.assertEqual(cmd["action"], "cron/install")
        self.assertEqual(cmd["body"]["schedule"], "0 3 * * *")

    def test_systemd_install_command(self):
        cmd = build_systemd_install_command(self.connector, "agent", "[Unit]\nDescription=Test")
        self.assertEqual(cmd["action"], "systemd/install")
        self.assertEqual(cmd["body"]["unit_content"], "[Unit]\nDescription=Test")

    def test_rollback_has_no_hmac(self):
        cmd = build_rollback_command(self.connector)
        self.assertEqual(cmd["action"], "overlay/rollback")
        # Rollback must NOT have HMAC headers (must work during uninstall)
        self.assertNotIn("X-Nexora-SaaS-Signature", cmd["headers"])
        self.assertNotIn("X-Nexora-SaaS-Timestamp", cmd["headers"])
