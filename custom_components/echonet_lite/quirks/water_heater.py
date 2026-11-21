"""Water-heater quirks: an aggregate entity assembled from profile EPCs."""

from __future__ import annotations

from typing import Any, override

from pyhems import BinaryCodec, NodeState

from homeassistant.components.water_heater import (
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import PRECISION_WHOLE, Platform, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..const import DOMAIN
from ..coordinator import EchonetLiteCoordinator
from ..entity import EchonetLiteEntity, setup_echonet_lite_device_platform
from ..prop import BinaryProp, NumericProp
from ..runtime import EchonetLiteConfigEntry
from .registry import QUIRKS, WaterHeaterQuirk


def async_setup_quirk_water_heaters(
    entry: EchonetLiteConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add aggregate water heaters declared by matching quirk profiles."""
    setup_echonet_lite_device_platform(
        entry,
        async_add_entities,
        platform_domain=Platform.WATER_HEATER.value,
        entity_factory=build_quirk_water_heaters,
    )


def build_quirk_water_heaters(
    coordinator: EchonetLiteCoordinator, node: NodeState
) -> list[Entity]:
    """Build a declaratively configured aggregate water-heater entity."""
    quirk = QUIRKS.water_heater_for(node)
    if quirk is None or (
        quirk.operation_epc not in node.get_epcs
        and quirk.operation_epc not in node.set_epcs
    ):
        return []
    return [EchonetLiteQuirkWaterHeater(coordinator, node, quirk)]


class EchonetLiteQuirkWaterHeater(EchonetLiteEntity, WaterHeaterEntity):
    """Water-heater aggregate assembled from a matching quirk profile."""

    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision: float = PRECISION_WHOLE

    def __init__(
        self,
        coordinator: EchonetLiteCoordinator,
        node: NodeState,
        quirk: WaterHeaterQuirk,
    ) -> None:
        """Initialize from validated declarative operation metadata."""
        super().__init__(coordinator, node)
        self._quirk = quirk
        self._operation_prop = BinaryProp(
            quirk.operation_epc,
            BinaryCodec(quirk.operation_on_edt, quirk.operation_off_edt),
        )
        self._temperature_prop: NumericProp | None = None
        if quirk.temperature_epc is not None:
            definition = QUIRKS.local_entity_definition(
                quirk.profile_id, quirk.temperature_epc
            )
            if definition is None:
                raise ValueError(
                    f"Water-heater profile {quirk.profile_id!r} has no local "
                    f"definition for temperature EPC 0x{quirk.temperature_epc:02X}"
                )
            self._temperature_prop = NumericProp.from_entity_def(
                definition, class_code=node.eoj.class_code
            )

        self._attr_translation_key = quirk.translation_key
        self._attr_unique_id = f"{node.device_key}-quirk_water_heater"
        self._subscribed_epcs = frozenset(
            epc
            for epc in (quirk.operation_epc, quirk.temperature_epc)
            if epc is not None
        )

        features = WaterHeaterEntityFeature(0)
        if quirk.operation_epc in node.set_epcs:
            features |= WaterHeaterEntityFeature.ON_OFF
            features |= WaterHeaterEntityFeature.OPERATION_MODE
            self._attr_operation_list = [STATE_OFF, quirk.operation_on_key]
        else:
            self._attr_operation_list = []
        self._attr_supported_features = features

        if self._temperature_prop is not None:
            if self._temperature_prop.min_value is not None:
                self._attr_min_temp = self._temperature_prop.min_value
            if self._temperature_prop.max_value is not None:
                self._attr_max_temp = self._temperature_prop.max_value

    @property
    @override
    def current_operation(self) -> str | None:
        """Return the configured operation as off or its named on state."""
        enabled = self._operation_prop.get(self._node)
        if enabled is None:
            return None
        return self._quirk.operation_on_key if enabled else STATE_OFF

    @property
    @override
    def native_target_temperature(self) -> float | None:
        """Expose a read-only temperature setting when the device reports one."""
        if self._temperature_prop is None:
            return None
        value = self._temperature_prop.get(self._node)
        return float(value) if value is not None else None

    @property
    @override
    def native_current_temperature(self) -> None:
        """Return no measured temperature; E1 is a setting, not a measurement."""
        return None

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the configured operation."""
        await self._send_prop(self._operation_prop, True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the configured operation."""
        await self._send_prop(self._operation_prop, False)

    @override
    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set off or the configured named operation."""
        if operation_mode == STATE_OFF:
            await self.async_turn_off()
            return
        if operation_mode != self._quirk.operation_on_key:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={"value": operation_mode},
            )
        await self.async_turn_on()
