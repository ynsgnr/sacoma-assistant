"""Configured household users and weight-range auto-selection.

The scale measures weight + impedance but doesn't know who is standing on it, and
the body-composition algorithm needs a profile (height/age/sex). We let the user
configure several people, each tagged with a weight range, and pick the matching
one by the measured weight — mirroring ``select_user`` in the library's reference
``scripts/ble_test.py``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from homeassistant.util import slugify
from sacoma import PeopleType, Sex, UserProfile

from .const import (
    CONF_AGE,
    CONF_ATHLETE,
    CONF_HEIGHT_CM,
    CONF_SEX,
    CONF_USER_ID,
    CONF_USER_NAME,
    CONF_USERS,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    DEFAULT_USER_ID,
    SEX_MALE,
)


@dataclass(frozen=True)
class ScaleUser:
    """One configured person: a weight range for matching plus the algorithm profile."""

    key: str          # stable slug used in entity unique ids and the per-user device
    name: str
    user_id: int      # scale account id (only meaningful when driving the display)
    weight_min: float
    weight_max: float
    profile: UserProfile

    def matches(self, weight_kg: float) -> bool:
        return self.weight_min <= weight_kg <= self.weight_max


def _user_from_dict(raw: Mapping[str, object], index: int, taken: set[str]) -> ScaleUser:
    name = str(raw.get(CONF_USER_NAME) or f"User {index + 1}")
    key = slugify(name) or f"user_{index}"
    while key in taken:                      # keep unique ids stable and distinct
        key = f"{key}_{index}"
    taken.add(key)
    return ScaleUser(
        key=key,
        name=name,
        user_id=int(raw.get(CONF_USER_ID, DEFAULT_USER_ID)),
        weight_min=float(raw[CONF_WEIGHT_MIN]),
        weight_max=float(raw[CONF_WEIGHT_MAX]),
        profile=UserProfile(
            height_cm=float(raw[CONF_HEIGHT_CM]),
            age=int(raw[CONF_AGE]),
            sex=Sex.MALE if raw.get(CONF_SEX) == SEX_MALE else Sex.FEMALE,
            people_type=PeopleType.SPORTMAN if raw.get(CONF_ATHLETE) else PeopleType.NORMAL,
        ),
    )


def users_from_config(source: Mapping[str, object]) -> list[ScaleUser]:
    """Parse the configured user list (entry data merged with options)."""
    taken: set[str] = set()
    return [
        _user_from_dict(raw, i, taken)
        for i, raw in enumerate(source.get(CONF_USERS, []))  # type: ignore[arg-type]
    ]


def select_user(users: Sequence[ScaleUser], weight_kg: float) -> ScaleUser | None:
    """Return the first user whose weight range contains ``weight_kg`` (else ``None``)."""
    return next((user for user in users if user.matches(weight_kg)), None)
