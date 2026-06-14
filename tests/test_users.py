"""User parsing + weight-range auto-selection.

``users.py`` imports ``homeassistant.util.slugify``, so these run under the HA test
harness and skip in a bare environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("homeassistant")  # users.py needs homeassistant.util.slugify
pytest.importorskip("sacoma")

from custom_components.sacoma_scale.users import select_user, users_from_config  # noqa: E402


def _config() -> dict:
    return {
        "users": [
            {"name": "Alex", "weight_min": 62, "weight_max": 67, "height_cm": 165,
             "age": 30, "sex": "male", "athlete": True, "user_id": 101},
            {"name": "Sam", "weight_min": 67, "weight_max": 80, "height_cm": 170,
             "age": 31, "sex": "female"},
        ]
    }


def test_users_parsed() -> None:
    users = users_from_config(_config())
    assert [u.name for u in users] == ["Alex", "Sam"]
    assert users[0].profile.height_cm == 165
    assert users[0].user_id == 101
    assert users[1].user_id == 0          # default when omitted


def test_select_by_weight_range() -> None:
    users = users_from_config(_config())
    assert select_user(users, 64.0).name == "Alex"
    assert select_user(users, 72.0).name == "Sam"
    assert select_user(users, 100.0) is None   # outside every configured range


def test_keys_are_unique() -> None:
    # Two users sharing a name must still get distinct entity keys.
    def named(lo: float, hi: float) -> dict:
        return {"name": "A", "weight_min": lo, "weight_max": hi,
                "height_cm": 170, "age": 30, "sex": "male"}

    users = users_from_config({"users": [named(1, 2), named(2, 3)]})
    assert users[0].key != users[1].key
