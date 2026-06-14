"""One BLE conversation with the scale: read a weigh-in and select the user.

Protocol framing, decoding and command sequencing live in :class:`sacoma.Session`;
this owns only the BLE transport and the orchestration, mirroring the library's
``scripts/ble_test.py``. Subscribe to the weight (FFB2) and result (FFB3)
notifications, read the live weight until it settles, pick the matching user, then
replay the app's sustained ``BA``/``BB``/``BD`` sync (with that user's profile) so the
scale shows body composition on its own display, and return the user with the result.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from sacoma import Measurement, Session

from .const import (
    DRIVE_INTERVAL_S,
    MIN_WEIGHT_KG,
    PUBLISH_SECONDS,
    READ_WEIGHT_TIMEOUT_S,
    RESULT_NOTIFY_UUID,
    SETTLE_READS,
    WEIGHT_EPSILON_KG,
    WEIGHT_NOTIFY_UUID,
    WRITE_CHAR_UUID,
)
from .users import ScaleUser, select_user

_LOGGER = logging.getLogger(__name__)
_NOTIFY_UUIDS = (WEIGHT_NOTIFY_UUID, RESULT_NOTIFY_UUID)


class ScaleSession:
    """Runs one connected weigh-in and returns the matched user + measurement."""

    def __init__(self, client: BleakClient, users: Sequence[ScaleUser]) -> None:
        self._client = client
        self._users = users
        self._proto = Session()
        self._live_weight = 0.0
        self._stable_weight: float | None = None
        self._pending_control = 0
        self._result: Measurement | None = None
        self._result_event = asyncio.Event()

    async def run(self, timeout: float) -> tuple[ScaleUser, Measurement] | None:
        """Return ``(user, result)``, or ``None`` if nothing arrived in time or no
        configured user's weight range matched the reading."""
        for uuid in _NOTIFY_UUIDS:
            await self._client.start_notify(uuid, self._on_frame)
        try:
            async with asyncio.timeout(timeout):
                await self._drive_flow()
        except TimeoutError:
            pass
        finally:
            for uuid in _NOTIFY_UUIDS:
                with contextlib.suppress(Exception):  # link is often already gone
                    await self._client.stop_notify(uuid)

        if self._result is None:
            return None
        user = select_user(self._users, self._result.weight_kg)
        if user is None:
            _LOGGER.debug("no configured user matches %.2f kg", self._result.weight_kg)
            return None
        return user, self._result

    def _on_frame(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Decode one notification frame (event-loop thread, synchronous)."""
        received = self._proto.feed(characteristic.uuid, bytes(data))
        if received.control:
            self._pending_control += 1
        if (measurement := received.measurement) is None:
            return
        if measurement.impedances_ohm:           # A3 result carries impedances; A2 doesn't
            self._result = measurement
            self._result_event.set()
        else:
            self._live_weight = measurement.weight_kg
            if measurement.is_stabilized:
                self._stable_weight = measurement.weight_kg

    # --- drive: replay the app's sync so the scale shows body composition ----------------
    async def _drive_flow(self) -> None:
        weight = await self._read_settled_weight()
        user = select_user(self._users, weight) if weight else None
        if user is None:
            await self._result_event.wait()  # nothing to drive; just wait for a result
        else:
            await self._publish(user)

    async def _read_settled_weight(self) -> float | None:
        """Return the weight that holds steady at its running peak (the user's weight)."""
        deadline = self._loop_time() + READ_WEIGHT_TIMEOUT_S
        acked = 0
        peak = 0.0
        last: float | None = None
        holds = 0
        while self._loop_time() < deadline and not self._result_event.is_set():
            acked = await self._ack_pending(acked)
            weight = self._stable_weight
            if weight is not None and weight >= MIN_WEIGHT_KG:
                if weight > peak + WEIGHT_EPSILON_KG:
                    peak, holds = weight, 0
                elif last is not None and abs(weight - last) <= WEIGHT_EPSILON_KG:
                    holds += 1
                    if holds >= SETTLE_READS:
                        return weight
                else:
                    holds = 0
                last = weight
            await asyncio.sleep(0.3)
        return self._stable_weight or (self._live_weight or None)

    async def _publish(self, user: ScaleUser) -> None:
        """Sustained profile sync until the result lands or the window closes."""
        deadline = self._loop_time() + PUBLISH_SECONDS
        acked = self._pending_control
        synced = False
        while self._loop_time() < deadline and not self._result_event.is_set():
            weight = self._stable_weight or self._live_weight
            if weight > 0:
                await self._write(
                    self._proto.sync(user.profile, weight, user.user_id, unix_time=int(time.time()))
                )
                if not synced:  # one-time user list + misc command, like the app
                    await self._write(self._proto.user_list([(user.profile, weight, user.user_id)]))
                    await self._write(self._proto.other())
                    synced = True
            acked = await self._ack_pending(acked)
            await asyncio.sleep(DRIVE_INTERVAL_S)

    async def _ack_pending(self, acked: int) -> int:
        """Ack any control frames the scale has sent since ``acked``; return the new count."""
        if self._pending_control > acked:
            await self._write(self._proto.ack())
            return self._pending_control
        return acked

    async def _write(self, frames: list[bytes]) -> None:
        for frame in frames:
            try:
                await self._client.write_gatt_char(WRITE_CHAR_UUID, frame, response=False)
            except Exception:  # noqa: BLE001 - a dropped write shouldn't abort the session
                _LOGGER.debug("FFB1 write failed", exc_info=True)

    @staticmethod
    def _loop_time() -> float:
        return asyncio.get_running_loop().time()
