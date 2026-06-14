"""Sensor platform for the SACOMA smart scale (one set of sensors per user)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricResistance,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from sacoma import BodyComposition

from . import SacomaConfigEntry
from .coordinator import SacomaScaleCoordinator, UserState
from .entity import SacomaUserEntity
from .users import ScaleUser


@dataclass(frozen=True, kw_only=True)
class SacomaSensorDescription(SensorEntityDescription):
    """Describes a sensor and how to derive its value from a user's latest reading."""

    value_fn: Callable[[UserState], StateType]


def _body(accessor: Callable[[BodyComposition], StateType]) -> Callable[[UserState], StateType]:
    """Wrap an accessor that needs the computed BodyComposition."""
    return lambda state: accessor(state.body) if state.body is not None else None


SENSORS: tuple[SacomaSensorDescription, ...] = (
    SacomaSensorDescription(
        key="weight",
        translation_key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        # Always available once a reading lands, even if body composition didn't compute.
        value_fn=lambda s: s.body.weight_kg if s.body else s.measurement.weight_kg,
    ),
    SacomaSensorDescription(
        key="bmi",
        translation_key="bmi",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.bmi),
    ),
    SacomaSensorDescription(
        key="body_fat",
        translation_key="body_fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.body_fat_percent),
    ),
    SacomaSensorDescription(
        key="subcutaneous_fat",
        translation_key="subcutaneous_fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.subcutaneous_fat_percent),
    ),
    SacomaSensorDescription(
        key="visceral_fat",
        translation_key="visceral_fat",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.visceral_fat),
    ),
    SacomaSensorDescription(
        key="muscle",
        translation_key="muscle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.muscle_percent),
    ),
    SacomaSensorDescription(
        key="skeletal_muscle",
        translation_key="skeletal_muscle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.skeletal_muscle_percent),
    ),
    SacomaSensorDescription(
        key="body_water",
        translation_key="body_water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.body_water_percent),
    ),
    SacomaSensorDescription(
        key="protein",
        translation_key="protein",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.protein_percent),
    ),
    SacomaSensorDescription(
        key="bone_mass",
        translation_key="bone_mass",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_body(lambda b: b.bone_mass_kg),
    ),
    SacomaSensorDescription(
        key="bmr",
        translation_key="bmr",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_body(lambda b: b.bmr_kcal),
    ),
    SacomaSensorDescription(
        key="metabolic_age",
        translation_key="metabolic_age",
        native_unit_of_measurement=UnitOfTime.YEARS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_body(lambda b: b.metabolic_age),
    ),
    SacomaSensorDescription(
        key="body_score",
        translation_key="body_score",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_body(lambda b: b.body_score),
    ),
    SacomaSensorDescription(
        key="whr",
        translation_key="whr",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_body(lambda b: b.whr),
    ),
    SacomaSensorDescription(
        key="impedance",
        translation_key="impedance",
        native_unit_of_measurement=UnitOfElectricResistance.OHM,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.measurement.impedance,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SacomaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a sensor set for each configured user."""
    coordinator = entry.runtime_data
    async_add_entities(
        SacomaSensor(coordinator, user, description)
        for user in coordinator.users
        for description in SENSORS
    )


class SacomaSensor(SacomaUserEntity, SensorEntity):
    """A single derived value from one user's latest reading."""

    entity_description: SacomaSensorDescription

    def __init__(
        self,
        coordinator: SacomaScaleCoordinator,
        user: ScaleUser,
        description: SacomaSensorDescription,
    ) -> None:
        super().__init__(coordinator, user)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{user.key}_{description.key}"

    @property
    def native_value(self) -> StateType:
        state = self.user_state
        return self.entity_description.value_fn(state) if state is not None else None
