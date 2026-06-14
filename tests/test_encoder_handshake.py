"""Lock the integration's contract with the sacoma command encoder.

``ScaleSession`` drives the scale by writing FFB1 command frames that
``sacoma.Session`` builds via ``sacoma.encoder``. The encoder now embeds the
user's profile (height/age/sex) and account id in the BA sync, so we check those
fields land where the session expects, against the real library.
"""
from __future__ import annotations

import pytest

sacoma = pytest.importorskip("sacoma")

CMD_REPLY = 0xB0
CMD_SYNC = 0xBA
CMD_USER_LIST = 0xBB
CMD_OTHER = 0xBD


def _reassemble(frames: list[bytes]) -> bytes:
    from sacoma import FrameAssembler

    assembler = FrameAssembler()
    payload = None
    for frame in frames:
        out = assembler.add_frame(frame)
        if out is not None:
            payload = out
    assert payload is not None, "frames never reassembled to a complete payload"
    return payload


def _profile():
    from sacoma import Sex, UserProfile

    return UserProfile(height_cm=165, age=30, sex=Sex.MALE)


def test_handshake_commands_roundtrip() -> None:
    from sacoma import encoder

    profile = _profile()
    cases = {
        CMD_SYNC: encoder.encode_sync(0, profile, 64.77, 101, unix_time=1_700_000_000),
        CMD_USER_LIST: encoder.encode_user_list(1, [(profile, 64.77, 101)]),
        CMD_REPLY: encoder.encode_reply(2),
        CMD_OTHER: encoder.encode_other(3),
    }
    for expected_cmd, frames in cases.items():
        assert frames, "encoder produced no frames"
        assert all(len(f) == 20 for f in frames), "frames must be 20 bytes"
        assert _reassemble(frames)[0] == expected_cmd


def test_sync_carries_profile_and_weight() -> None:
    """The BA sync must carry the account id, height and stabilized weight."""
    from sacoma import encoder
    from sacoma.encoder import STABILIZED_FLAG

    payload = _reassemble(encoder.encode_sync(0, _profile(), 64.77, 101, unix_time=1_700_000_000))
    # ba | time(4) | 00 78 | userId(4) | height(1) | weight(2) | age|sex(1) | flags(1)
    assert payload[0] == CMD_SYNC
    assert int.from_bytes(payload[7:11], "big") == 101      # account id
    assert payload[11] == 165                               # height cm
    raw = int.from_bytes(payload[12:14], "big")
    assert raw & STABILIZED_FLAG
    assert (raw & 0x7FFF) == round(64.77 * 100)
    assert payload[14] & 0x7F == 30                         # age
    assert payload[14] & 0x80                               # male bit
