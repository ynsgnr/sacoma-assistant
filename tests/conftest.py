"""Shared fixtures and sample data for the SACOMA scale tests."""
from __future__ import annotations

import pytest

# Two real A3 result captures (subject: 165 cm, 30 y, male, athlete), reused from the
# sacoma library's own test vectors. Each is the pair of 20-byte BLE notification frames
# that, once reassembled, decode to the weights/impedances below.
DISPLAY_FRAMES = [
    bytes.fromhex("011a00a31900fd020000d30b850b4e0a740af615"),
    bytes.fromhex("011a0100960a0a09ec092d09b600000000000014"),
]
DISPLAY_WEIGHT_KG = 64.77
DISPLAY_IMPEDANCES = [21.1, 294.9, 289.4, 267.6, 280.6, 15.0, 257.0, 254.0, 234.9, 248.6]


@pytest.fixture
def display_frames() -> list[bytes]:
    return list(DISPLAY_FRAMES)
