"""BLE lifecycle coordinator for the SACOMA smart scale.

Listens for the scale's advertisements (it advertises only while in use), opens a
short-lived GATT connection, and hands it to a :class:`~.session.ScaleSession`, which
reads the weigh-in and selects the matching user. The coordinator then computes that
user's body composition (``sacoma.compute``) and publishes it into a per-user state
map the sensors read from.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from sacoma import BodyComposition, Measurement, UserProfile, compute

from .const import DOMAIN, MEASUREMENT_TIMEOUT_S
from .session import ScaleSession
from .users import ScaleUser

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserState:
    """The latest reading attributed to one user (``body`` is None if uncomputable)."""

    measurement: Measurement
    body: BodyComposition | None


type ScaleData = dict[str, UserState]   # user key -> latest state


class SacomaScaleCoordinator(DataUpdateCoordinator[ScaleData]):
    """Owns the BLE lifecycle and exposes per-user decoded state to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        address: str,
        device_name: str,
        users: Sequence[ScaleUser],
        *,
        drive: bool = False,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{address}",
            update_interval=None,  # push device: we call async_set_updated_data() ourselves
        )
        self.address = address
        self.device_name = device_name
        self.users = list(users)
        self.drive = drive
        self._unload_callbacks: list[Callable[[], None]] = []
        # Set synchronously in the advertisement callback to keep one session per weigh-in.
        self._busy = False
        self.data = {}

    async def async_start(self) -> None:
        """Register for advertisements from this scale."""
        self._unload_callbacks.append(
            bluetooth.async_register_callback(
                self.hass,
                self._on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )

    async def async_stop(self) -> None:
        """Tear down advertisement listeners."""
        while self._unload_callbacks:
            self._unload_callbacks.pop()()

    @callback
    def _on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """The scale is awake — schedule a read, unless one is already running."""
        if self._busy:
            return
        self._busy = True
        self.config_entry.async_create_background_task(
            self.hass, self._async_read_measurement(), name=f"{DOMAIN}_read_{self.address}"
        )

    async def _async_read_measurement(self) -> None:
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                _LOGGER.debug("%s no longer in range", self.address)
                return
            await self._async_session(ble_device)
        except Exception:  # noqa: BLE001 - connection drops are routine for a scale
            _LOGGER.debug("measurement session for %s failed", self.address, exc_info=True)
        finally:
            self._busy = False

    async def _async_session(self, ble_device: BLEDevice) -> None:
        client: BleakClientWithServiceCache = await establish_connection(
            BleakClientWithServiceCache, ble_device, self.address
        )
        try:
            result = await ScaleSession(client, self.users, drive=self.drive).run(
                MEASUREMENT_TIMEOUT_S
            )
        finally:
            await client.disconnect()

        if result is None:
            return
        user, measurement = result
        state = UserState(measurement, self._compute(measurement, user.profile))
        self.async_set_updated_data({**self.data, user.key: state})

    @staticmethod
    def _compute(measurement: Measurement, profile: UserProfile) -> BodyComposition | None:
        """Run WLA25, tolerating its documented validation / under-18 failures."""
        try:
            return compute(measurement, profile)
        except (ValueError, NotImplementedError) as err:
            _LOGGER.debug("body composition unavailable: %s", err)
            return None
