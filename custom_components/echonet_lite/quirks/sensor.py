"""Sensor quirks: raw diagnostic sensors, value suppression and daily counters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from pyhems import NodeState

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from ..entity import (
    EchonetLiteDescribedEntity,
    EchonetLiteEntityDescription,
    setup_common_platform,
)
from ..runtime import EchonetLiteConfigEntry
from .platform import with_mixin
from .registry import QUIRKS, RawSensorDefinition


def quirk_sensor[T: type](base: T) -> T:
    """Return the sensor entity class with quirk support."""
    return with_mixin(SuppressibleSensorMixin, base)


def async_setup_quirk_sensors(
    entry: EchonetLiteConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add raw diagnostic sensors declared by matching quirk profiles."""
    setup_common_platform(
        entry,
        async_add_entities,
        Platform.SENSOR.value,
        _RAW_DESCRIPTIONS,
        EchonetLiteRawSensor,
    )


class SuppressibleSensorMixin:
    """Quirk behavior for numeric sensors.

    - ``native_value`` is None while a profile's raw-value condition is true.
    - ``daily_reset`` counters report the start of the local day as
      ``last_reset``. The device clears them at midnight, so a lower reading
      during the day is recorded as a small negative change instead of a
      meter reset that counts the whole value again.
    """

    _daily_reset: bool = False

    def __init__(self, coordinator: Any, node: Any, description: Any) -> None:
        """Initialize the upstream entity and read the daily-reset flag."""
        super().__init__(coordinator, node, description)  # type: ignore[call-arg]
        self._daily_reset = QUIRKS.daily_reset(
            node, description.translation_key or "", description.epc
        )

    @property
    def native_value(self) -> Any:
        """Return None while suppressed, else the upstream value."""
        self_: Any = self
        if QUIRKS.should_suppress_value(self_._node, self_.description.epc):
            return None
        return super().native_value  # type: ignore[misc]

    @property
    def last_reset(self) -> datetime | None:
        """Return local midnight for counters the device clears every day."""
        if not self._daily_reset:
            return super().last_reset  # type: ignore[misc]
        return dt_util.start_of_local_day()


@dataclass(frozen=True, kw_only=True)
class EchonetLiteRawSensorEntityDescription(
    SensorEntityDescription, EchonetLiteEntityDescription
):
    """Description for a quirk-provided raw EDT diagnostic sensor."""

    profile_id: str
    expected_length: int | None = None

    @classmethod
    def from_quirk(
        cls, definition: RawSensorDefinition
    ) -> EchonetLiteRawSensorEntityDescription:
        """Build a Home Assistant description from a raw quirk definition."""
        return cls(
            key=f"raw_{definition.profile_id}_{definition.epc:02x}",
            translation_key=definition.id,
            epc=definition.epc,
            entity_category=EntityCategory.DIAGNOSTIC,
            profile_id=definition.profile_id,
            expected_length=definition.expected_length,
        )

    @override
    def should_create(self, node: NodeState) -> bool:
        """Create only for a matching profile that advertises the EPC."""
        return self.epc in node.get_epcs and QUIRKS.profile_matches(
            self.profile_id, node
        )


_RAW_DESCRIPTIONS: dict[int, list[EchonetLiteRawSensorEntityDescription]] = {
    class_code: [
        EchonetLiteRawSensorEntityDescription.from_quirk(definition)
        for definition in definitions
    ]
    for class_code, definitions in QUIRKS.raw_sensors.items()
}


class EchonetLiteRawSensor(
    EchonetLiteDescribedEntity[EchonetLiteRawSensorEntityDescription], SensorEntity
):
    """Diagnostic sensor exposing an unknown property as hexadecimal EDT."""

    @property
    @override
    def native_value(self) -> str | None:
        """Return the complete EDT as uppercase hexadecimal text."""
        edt = self._node.properties.get(self.description.epc)
        return None if edt is None else f"0x{edt.hex().upper()}"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose byte length and unsigned interpretation for observation."""
        attributes: dict[str, Any] = dict(super().extra_state_attributes or {})
        edt = self._node.properties.get(self.description.epc)
        if edt is None:
            return attributes
        attributes["raw_length"] = len(edt)
        attributes["raw_unsigned"] = int.from_bytes(edt, "big") if edt else 0
        if self.description.expected_length is not None:
            attributes["expected_length"] = self.description.expected_length
            attributes["length_matches"] = len(edt) == self.description.expected_length
        return attributes
