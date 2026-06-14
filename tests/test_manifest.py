"""Static checks on the integration's manifest and HACS metadata.

These run without Home Assistant installed — they guard the wiring that the rest
of the integration depends on (domain, discovery matcher, requirements).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "sacoma_scale"
FFB0 = "0000ffb0-0000-1000-8000-00805f9b34fb"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_core_fields() -> None:
    manifest = _load(COMPONENT / "manifest.json")
    assert manifest["domain"] == "sacoma_scale"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_push"
    assert "bluetooth_adapters" in manifest["dependencies"]


def test_manifest_bluetooth_matcher() -> None:
    manifest = _load(COMPONENT / "manifest.json")
    matchers = manifest["bluetooth"]
    # Discover by the FFB0 service UUID (universal) or the advertised name; both must
    # be connectable, since the integration reads over a GATT connection.
    assert any(m.get("service_uuid") == FFB0 and m.get("connectable") for m in matchers)
    assert any(m.get("local_name") and m.get("connectable") for m in matchers)


def test_manifest_requires_sacoma() -> None:
    manifest = _load(COMPONENT / "manifest.json")
    assert any(req.startswith("sacoma==") for req in manifest["requirements"])


def test_hacs_metadata() -> None:
    hacs = _load(ROOT / "hacs.json")
    assert hacs["name"]
    assert "homeassistant" in hacs


def test_translations_match_strings() -> None:
    strings = _load(COMPONENT / "strings.json")
    english = _load(COMPONENT / "translations" / "en.json")
    assert strings["entity"]["sensor"].keys() == english["entity"]["sensor"].keys()
