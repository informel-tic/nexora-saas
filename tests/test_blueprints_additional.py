"""Tests for nexora_node_sdk.blueprints — load and plan resolution."""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


def _write_profile(directory: Path, slug: str, data: str) -> None:
    bp_dir = directory / slug
    bp_dir.mkdir(parents=True, exist_ok=True)
    (bp_dir / "profile.yaml").write_text(data, encoding="utf-8")


_SIMPLE_YAML = textwrap.dedent("""\
    slug: myapp
    name: My App
    description: A test blueprint
    activity: tech
    profiles:
      - standard
    recommended_apps:
      - nextcloud
    subdomains:
      - cloud
    security_baseline:
      https: required
    monitoring_baseline:
      - uptime
    pra_baseline:
      - daily_backup
    portal:
      theme: blue
""")


class TestLoadBlueprints(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_empty_root_returns_empty_list(self):
        from nexora_node_sdk.blueprints import load_blueprints

        result = load_blueprints(self.root / "nonexistent")
        self.assertEqual(result, [])

    def test_loads_single_blueprint(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        blueprints = load_blueprints(self.root)
        self.assertEqual(len(blueprints), 1)
        bp = blueprints[0]
        self.assertEqual(bp.slug, "myapp")
        self.assertEqual(bp.name, "My App")
        self.assertEqual(bp.description, "A test blueprint")
        self.assertEqual(bp.activity, "tech")

    def test_blueprint_profiles_list(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = load_blueprints(self.root)[0]
        self.assertIn("standard", bp.profiles)

    def test_blueprint_recommended_apps(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = load_blueprints(self.root)[0]
        self.assertIn("nextcloud", bp.recommended_apps)

    def test_blueprint_subdomains(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = load_blueprints(self.root)[0]
        self.assertIn("cloud", bp.subdomains)

    def test_blueprint_security_baseline(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = load_blueprints(self.root)[0]
        self.assertIsInstance(bp.security_baseline, dict)
        self.assertEqual(bp.security_baseline.get("https"), "required")

    def test_blueprint_portal(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = load_blueprints(self.root)[0]
        self.assertEqual(bp.portal.get("theme"), "blue")

    def test_loads_multiple_blueprints(self):
        from nexora_node_sdk.blueprints import load_blueprints

        for slug in ("alpha", "beta", "gamma"):
            _write_profile(self.root, slug, f"slug: {slug}\nname: {slug.title()}\n")
        blueprints = load_blueprints(self.root)
        self.assertEqual(len(blueprints), 3)
        slugs = {bp.slug for bp in blueprints}
        self.assertEqual(slugs, {"alpha", "beta", "gamma"})

    def test_slug_defaults_to_directory_name(self):
        from nexora_node_sdk.blueprints import load_blueprints

        # profile.yaml with no slug — slug should default to parent dir name
        _write_profile(self.root, "dirslug", "name: Dir Blueprint\n")
        bp = load_blueprints(self.root)[0]
        self.assertEqual(bp.slug, "dirslug")

    def test_name_defaults_from_directory_name(self):
        from nexora_node_sdk.blueprints import load_blueprints

        _write_profile(self.root, "my-app", "")
        bp = load_blueprints(self.root)[0]
        self.assertEqual(bp.name, "My App")

    def test_invalid_yaml_still_produces_blueprint(self):
        from nexora_node_sdk.blueprints import load_blueprints

        # Empty file → should produce blueprint with defaults
        _write_profile(self.root, "empty-bp", "")
        blueprints = load_blueprints(self.root)
        self.assertEqual(len(blueprints), 1)
        self.assertIsInstance(blueprints[0].recommended_apps, list)


class TestResolveBlueprint(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_resolve_existing_slug(self):
        from nexora_node_sdk.blueprints import resolve_blueprint

        _write_profile(self.root, "myapp", _SIMPLE_YAML)
        bp = resolve_blueprint(self.root, "myapp")
        self.assertIsNotNone(bp)
        self.assertEqual(bp.slug, "myapp")

    def test_returns_none_for_missing_slug(self):
        from nexora_node_sdk.blueprints import resolve_blueprint

        bp = resolve_blueprint(self.root, "nonexistent")
        self.assertIsNone(bp)


class TestResolveBlueprintPlan(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _mock_profile(self, install_mode="domain_path", path="/"):
        return {
            "app_id": "nextcloud",
            "install_mode": install_mode,
            "automation": "fully_automated",
            "safe_defaults": {"path": path},
        }

    def _mock_preflight(self, allowed=True):
        return {
            "allowed": allowed,
            "status": "ok" if allowed else "blocked",
            "blocking_issues": [] if allowed else ["disk_too_small"],
            "warnings": [],
            "manual_review_required": False,
        }

    def test_plan_structure_for_simple_blueprint(self):
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="myapp",
            name="My App",
            description="",
            activity="tech",
            profiles=[],
            recommended_apps=["nextcloud"],
            subdomains=["cloud"],
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        with patch("nexora_node_sdk.blueprints.resolve_app_profile", return_value=self._mock_profile()), \
             patch("nexora_node_sdk.blueprints.build_install_preflight", return_value=self._mock_preflight()):
            plan = resolve_blueprint_plan(bp, "example.tld")

        self.assertEqual(plan["blueprint"], "myapp")
        self.assertEqual(plan["domain"], "example.tld")
        self.assertIn("app_plans", plan)
        self.assertIn("status", plan)
        self.assertEqual(len(plan["app_plans"]), 1)

    def test_plan_shows_ready_when_all_ok(self):
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="s",
            name="S",
            description="",
            activity="x",
            profiles=[],
            recommended_apps=["nextcloud"],
            subdomains=[],
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        with patch("nexora_node_sdk.blueprints.resolve_app_profile", return_value=self._mock_profile()), \
             patch("nexora_node_sdk.blueprints.build_install_preflight", return_value=self._mock_preflight(True)):
            plan = resolve_blueprint_plan(bp, "example.tld")

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["allowed"])

    def test_plan_blocked_when_app_profile_error(self):
        from nexora_node_sdk.app_profiles import AppProfileError
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="s",
            name="S",
            description="",
            activity="x",
            profiles=[],
            recommended_apps=["unknown_app"],
            subdomains=[],
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        with patch("nexora_node_sdk.blueprints.resolve_app_profile", side_effect=AppProfileError("no profile")):
            plan = resolve_blueprint_plan(bp, "example.tld")

        self.assertEqual(plan["status"], "blocked")
        self.assertFalse(plan["allowed"])

    def test_plan_uses_subdomain_for_target_domain(self):
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="s",
            name="S",
            description="",
            activity="x",
            profiles=[],
            recommended_apps=["gitea"],
            subdomains=["git"],
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        with patch("nexora_node_sdk.blueprints.resolve_app_profile", return_value=self._mock_profile()), \
             patch("nexora_node_sdk.blueprints.build_install_preflight", return_value=self._mock_preflight(True)):
            plan = resolve_blueprint_plan(bp, "example.tld")

        topology = plan["topology"]
        self.assertEqual(topology[0]["domain"], "git.example.tld")
        self.assertEqual(topology[0]["subdomain"], "git")

    def test_plan_empty_recommended_apps(self):
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="empty",
            name="Empty",
            description="",
            activity="x",
            profiles=[],
            recommended_apps=[],
            subdomains=[],
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        plan = resolve_blueprint_plan(bp, "example.tld")
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["app_plans"], [])

    def test_plan_subdomain_only_mode_missing_subdomain_blocks(self):
        from nexora_node_sdk.blueprints import resolve_blueprint_plan
        from nexora_node_sdk.models import Blueprint

        bp = Blueprint(
            slug="s",
            name="S",
            description="",
            activity="x",
            profiles=[],
            recommended_apps=["roundcube"],
            subdomains=[],  # No subdomain provided
            security_baseline={},
            monitoring_baseline=[],
            pra_baseline=[],
            portal={},
        )

        with patch("nexora_node_sdk.blueprints.resolve_app_profile",
                   return_value=self._mock_profile(install_mode="subdomain_only")), \
             patch("nexora_node_sdk.blueprints.build_install_preflight",
                   return_value=self._mock_preflight(True)):
            plan = resolve_blueprint_plan(bp, "example.tld")

        # Should have blocking issue for missing subdomain
        app_plan = plan["app_plans"][0]
        self.assertIn("missing_blueprint_subdomain_for_subdomain_only_profile", app_plan["blocking_issues"])


class TestLoadBlueprintsFromActualFilesystem(unittest.TestCase):
    """Verify the real blueprints/ directory is loadable."""

    def test_load_real_blueprints_dir(self):
        from nexora_node_sdk.blueprints import load_blueprints

        root = Path("blueprints")
        if not root.exists():
            self.skipTest("blueprints/ directory not present")

        blueprints = load_blueprints(root)
        # Should load without errors; may be empty if no profile.yaml files
        self.assertIsInstance(blueprints, list)


if __name__ == "__main__":
    unittest.main()
