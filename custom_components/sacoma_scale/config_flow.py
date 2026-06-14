"""Config flow for the SACOMA smart scale.

Setup runs: pick the device (auto-discovered or chosen manually) -> name it and set
the drive option -> add one or more household users. Each user carries a weight range
(used to auto-select who stepped on the scale) and the body profile the WLA25
algorithm needs. The same device + user collection backs the options flow.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ADD_ANOTHER,
    CONF_ADDRESS,
    CONF_AGE,
    CONF_ATHLETE,
    CONF_DEVICE_NAME,
    CONF_DRIVE,
    CONF_HEIGHT_CM,
    CONF_SEX,
    CONF_USER_ID,
    CONF_USER_NAME,
    CONF_USERS,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    DEFAULT_AGE,
    DEFAULT_DRIVE,
    DEFAULT_HEIGHT_CM,
    DEFAULT_USER_ID,
    DOMAIN,
    LOCAL_NAME,
    SERVICE_UUID,
    SEX_FEMALE,
    SEX_MALE,
)

DEFAULT_TITLE = "SACOMA Smart Scale"


def _device_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME) or DEFAULT_TITLE
            ): str,
            vol.Required(CONF_DRIVE, default=defaults.get(CONF_DRIVE, DEFAULT_DRIVE)): cv.boolean,
        }
    )


def _user_schema() -> vol.Schema:
    weight = vol.All(vol.Coerce(float), vol.Range(min=2, max=400))
    return vol.Schema(
        {
            vol.Required(CONF_USER_NAME): str,
            vol.Required(CONF_WEIGHT_MIN): weight,
            vol.Required(CONF_WEIGHT_MAX): weight,
            vol.Required(CONF_HEIGHT_CM, default=DEFAULT_HEIGHT_CM): vol.All(
                vol.Coerce(float), vol.Range(min=80, max=250)
            ),
            vol.Required(CONF_AGE, default=DEFAULT_AGE): vol.All(
                vol.Coerce(int), vol.Range(min=10, max=120)
            ),
            vol.Required(CONF_SEX, default=SEX_MALE): vol.In(
                {SEX_MALE: "Male", SEX_FEMALE: "Female"}
            ),
            vol.Required(CONF_ATHLETE, default=False): cv.boolean,
            vol.Optional(CONF_USER_ID, default=DEFAULT_USER_ID): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
            vol.Required(CONF_ADD_ANOTHER, default=False): cv.boolean,
        }
    )


def _is_scale(info: BluetoothServiceInfoBleak) -> bool:
    """Match SACOMA/ICOMON scales among discovered BLE devices.

    Prefer the FFB0 service UUID (universal); fall back to the advertised name for
    units that don't list the service in their advertisement.
    """
    return SERVICE_UUID in info.service_uuids or info.name == LOCAL_NAME


class _DeviceUsersFlow:
    """Shared device-name/drive step + multi-user 'add another' loop.

    Mixed into both the config and options flows; subclasses supply ``_finish`` (how
    to persist) and ``_device_defaults`` (what to pre-fill the device form with).
    """

    _device_name: str
    _drive: bool
    _users: list[dict[str, Any]]

    def _start_collection(self) -> None:
        self._device_name = ""
        self._drive = DEFAULT_DRIVE
        self._users = []

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._device_name = user_input[CONF_DEVICE_NAME]
            self._drive = user_input[CONF_DRIVE]
            return await self.async_step_add_user()
        return self.async_show_form(
            step_id="device", data_schema=_device_schema(self._device_defaults())
        )

    async def async_step_add_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_WEIGHT_MIN] >= user_input[CONF_WEIGHT_MAX]:
                errors["base"] = "invalid_weight_range"
            else:
                add_another = user_input.pop(CONF_ADD_ANOTHER)
                self._users.append(user_input)
                if add_another:
                    return await self.async_step_add_user()
                return await self._finish()
        return self.async_show_form(
            step_id="add_user",
            data_schema=_user_schema(),
            errors=errors,
            description_placeholders={"index": str(len(self._users) + 1)},
        )

    async def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    def _device_defaults(self) -> dict[str, Any]:
        raise NotImplementedError


class SacomaConfigFlow(_DeviceUsersFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the SACOMA smart scale."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._adv_name: str | None = None
        # address -> dropdown label, and address -> advertised name (for the default name)
        self._discovered: dict[str, str] = {}
        self._discovered_names: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered by the Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._adv_name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._adv_name}
        self._start_collection()
        return await self.async_step_device()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a device to set up.

        The advertised name is customisable, so we don't rely on matching it: we
        prefer recognised scales (FFB0 service / known name) but fall back to listing
        every nearby connectable device, so a renamed scale is still selectable.
        """
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._adv_name = self._discovered_names.get(self._address, self._address)
            self._start_collection()
            return await self.async_step_device()

        current = self._async_current_ids()
        candidates: dict[str, str] = {}
        others: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            self._discovered_names[info.address] = info.name or info.address
            label = f"{info.name or 'Unknown'} ({info.address})"
            (candidates if _is_scale(info) else others)[info.address] = label

        self._discovered = candidates or others
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    def _device_defaults(self) -> dict[str, Any]:
        return {CONF_DEVICE_NAME: self._adv_name or DEFAULT_TITLE, CONF_DRIVE: DEFAULT_DRIVE}

    async def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._device_name or DEFAULT_TITLE,
            data={
                CONF_ADDRESS: self._address,
                CONF_DEVICE_NAME: self._device_name,
                CONF_DRIVE: self._drive,
                CONF_USERS: self._users,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SacomaOptionsFlow()


class SacomaOptionsFlow(_DeviceUsersFlow, OptionsFlow):
    """Re-enter the device name, drive option and the full user list after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._start_collection()
        return await self.async_step_device()

    def _device_defaults(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title="",
            data={
                CONF_DEVICE_NAME: self._device_name,
                CONF_DRIVE: self._drive,
                CONF_USERS: self._users,
            },
        )
