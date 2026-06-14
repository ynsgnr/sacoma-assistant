"""Lock the integration's contract with the sacoma library.

The coordinator's notification handler relies on two behaviours:

* feeding raw 20-byte frames to ``decode_frame`` yields a ``Measurement`` only
  once a full message is reassembled, and
* a *result* (A3) measurement is distinguishable from the live-weight (A2)
  stream by carrying the 10 segmental impedances.

If the library changes either, the coordinator's branching breaks — so we test
it here against real captures rather than mocking.
"""
from __future__ import annotations

import pytest

from .conftest import DISPLAY_IMPEDANCES, DISPLAY_WEIGHT_KG

sacoma = pytest.importorskip("sacoma")


def test_frames_decode_to_result(display_frames: list[bytes]) -> None:
    from sacoma import FrameAssembler, decode_frame

    assembler = FrameAssembler()
    measurement = None
    for frame in display_frames:
        out = decode_frame(frame, assembler)
        if out is not None:
            measurement = out

    assert measurement is not None, "A3 result never completed"
    assert measurement.weight_kg == pytest.approx(DISPLAY_WEIGHT_KG, abs=0.01)
    # The coordinator uses a non-empty impedance list as its 'this is a result' signal.
    assert measurement.impedances_ohm
    assert measurement.impedances_ohm == pytest.approx(DISPLAY_IMPEDANCES, abs=0.05)


def test_partial_frame_yields_nothing() -> None:
    from sacoma import FrameAssembler, decode_frame

    assembler = FrameAssembler()
    # First of a two-frame message must not yet produce a measurement.
    first = bytes.fromhex("011a00a31900fd020000d30b850b4e0a740af615")
    assert decode_frame(first, assembler) is None


def test_session_reassembles_channels_independently(display_frames: list[bytes]) -> None:
    """ScaleSession feeds each notify characteristic to sacoma.Session as a channel.

    The A3 result (FFB3) and the weight stream (FFB2) number their fragments
    independently, so their sequence numbers collide — the DISPLAY A3 spans two
    frames at sequence 0x01. Feeding a weight frame at the same sequence on the
    weight channel between them must not disturb the A3 reassembled on the result
    channel.
    """
    from sacoma import Session

    weight_ch, result_ch = "ffb2", "ffb3"
    a3_first, a3_second = display_frames
    # Valid single-frame A2 weight at the colliding sequence 0x01 (checksum 0x0f).
    weight_frame = bytes.fromhex("010700" + "a2011900edc600" + "00" * 9 + "0f")

    session = Session()
    assert session.feed(result_ch, a3_first).measurement is None      # first A3 fragment buffered
    weight = session.feed(weight_ch, weight_frame).measurement        # colliding-seq, other channel
    assert weight is not None and not weight.impedances_ohm
    measurement = session.feed(result_ch, a3_second).measurement      # A3 completes intact
    assert measurement is not None
    assert measurement.weight_kg == pytest.approx(DISPLAY_WEIGHT_KG, abs=0.01)
    assert measurement.impedances_ohm == pytest.approx(DISPLAY_IMPEDANCES, abs=0.05)


def test_compute_tolerates_validation_errors() -> None:
    """compute() raises on bad input; the coordinator swallows that to None."""
    from sacoma import Measurement, Sex, UserProfile
    from sacoma.calculations import compute

    profile = UserProfile(height_cm=170, age=30, sex=Sex.MALE)
    empty = Measurement(weight_kg=0.0, impedances_ohm=[0.0] * 10)
    with pytest.raises((ValueError, NotImplementedError)):
        compute(empty, profile)
