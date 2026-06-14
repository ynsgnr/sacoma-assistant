"""Base entity for SACOMA scale entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SacomaScaleCoordinator, UserState
from .users import ScaleUser


class SacomaUserEntity(CoordinatorEntity[SacomaScaleCoordinator]):
    """Common wiring for entities belonging to one configured user.

    Each user is its own device, linked to the physical scale via ``via_device`` so
    every household member's readings group separately under the one scale.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: SacomaScaleCoordinator, user: ScaleUser) -> None:
        super().__init__(coordinator)
        self._user = user
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.address}_{user.key}")},
            via_device=(DOMAIN, coordinator.address),
            name=f"{coordinator.device_name} {user.name}",
        )

    @property
    def user_state(self) -> UserState | None:
        """The latest reading attributed to this user, if any."""
        return self.coordinator.data.get(self._user.key)

    @property
    def available(self) -> bool:
        return super().available and self.user_state is not None
