import tempfile
from pathlib import Path

import yaml

from nexora_node_sdk.surface_registry import SurfaceRegistry


def test_surface_registry_parity_and_coverage():
    catalog = {
        "version": 1,
        "updated_at": "2026-03-29T00:00:00Z",
        "capabilities": [
            {
                "id": "cap_one",
                "domain": "alpha",
                "surfaces": {"rest": ["/a"], "mcp": ["m1"], "console": []},
            },
            {
                "id": "cap_two",
                "domain": "beta",
                "surfaces": {"rest": ["/b"], "mcp": [], "console": []},
            },
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "capabilities.yaml"
        p.write_text(yaml.safe_dump(catalog), encoding="utf-8")
        reg = SurfaceRegistry(path=p)
        assert reg.get_capability("cap_one")["domain"] == "alpha"
        assert len(reg.list_all()) == 2
        assert len(reg.list_by_surface("rest")) == 2
        assert len(reg.list_by_surface("mcp")) == 1
        assert len(reg.list_by_domain("alpha")) == 1
        report = reg.parity_report()
        assert report["total_capabilities"] == 2
        assert report["full_parity_count"] == 0
        assert reg.coverage_score() == 0.0
        payload = reg.to_payload()
        assert payload["total_capabilities"] == 2
        assert "coverage_score" in payload
