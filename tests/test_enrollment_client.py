import hashlib
import unittest

from nexora_node_sdk import enrollment_client


class EnrollmentClientTests(unittest.TestCase):
    def test_build_attestation_response_deterministic(self):
        r1 = enrollment_client.build_attestation_response(challenge="c", node_id="n", token_id="t")
        r2 = enrollment_client.build_attestation_response(challenge="c", node_id="n", token_id="t")
        self.assertEqual(r1, r2)
        expected = hashlib.sha256(b"c:n:t").hexdigest()
        self.assertEqual(r1, expected)

    def test_different_inputs_different_hash(self):
        a = enrollment_client.build_attestation_response(challenge="c1", node_id="n", token_id="t")
        b = enrollment_client.build_attestation_response(challenge="c2", node_id="n", token_id="t")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
