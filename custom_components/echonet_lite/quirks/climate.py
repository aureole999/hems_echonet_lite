"""Climate quirks: vendor fan-mode labels, target humidity and Home/Away presets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.climate.const import PRESET_AWAY, PRESET_HOME
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from ..const import DOMAIN, EPC_FAN_SPEED
from ..prop import BinaryProp, NumericProp
from .platform import with_mixin
from .registry import QUIRKS, ClimateQuirk


def quirk_climate[T: type](base: T) -> T:
    """Return the climate entity class with quirk support."""
    return with_mixin(QuirkClimateMixin, base)


def _not_writable(epc: int | None) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="epc_not_writable",
        translation_placeholders={
            "epc_list": "not configured" if epc is None else f"0x{epc:02X}"
        },
    )


class QuirkClimateMixin:
    """Apply a matching ``ClimateQuirk`` on top of the upstream climate entity.

    Nodes without a matching profile keep the upstream behavior unchanged.
    """

    _climate_quirk: ClimateQuirk | None

    def __init__(self, coordinator: Any, node: Any, description: Any) -> None:
        """Initialize the upstream entity, then apply the matching quirk."""
        super().__init__(coordinator, node, description)  # type: ignore[call-arg]
        quirk = self._climate_quirk = QUIRKS.climate_for(node)
        self._target_humidity_prop: NumericProp | None = None
        self._power_saving_prop: BinaryProp | None = None
        self._fan_key_to_label: dict[str, str] = {}
        self._fan_label_to_key: dict[str, str] = {}
        if quirk is None:
            return
        self_: Any = self
        if quirk.translation_key is not None:
            self_._attr_translation_key = quirk.translation_key
        features = self_._attr_supported_features
        class_code = node.eoj.class_code

        if EPC_FAN_SPEED in node.set_epcs and quirk.fan_mode_labels:
            protocol_options = description.fan_mode_prop.options
            configured = quirk.fan_mode_labels
            self._fan_key_to_label = {
                key: label for key, label in configured if key in protocol_options
            }
            fan_modes = [
                label for key, label in configured if key in self._fan_key_to_label
            ]
            if not quirk.strict_fan_modes:
                configured_keys = {key for key, _label in configured}
                for key in protocol_options:
                    if key not in configured_keys:
                        self._fan_key_to_label[key] = key
                        fan_modes.append(key)
            self_._attr_fan_modes = fan_modes
            self._fan_label_to_key = {
                label: key for key, label in self._fan_key_to_label.items()
            }

        if (epc := quirk.target_humidity_epc) is not None:
            self._target_humidity_prop = NumericProp.from_registry(class_code, epc)
            if epc in node.get_epcs or epc in node.set_epcs:
                self_._subscribed_epcs |= {epc}
            if epc in node.set_epcs:
                features |= ClimateEntityFeature.TARGET_HUMIDITY

        if (epc := quirk.power_saving_preset_epc) is not None:
            self._power_saving_prop = BinaryProp.from_registry(class_code, epc)
            if epc in node.get_epcs or epc in node.set_epcs:
                self_._subscribed_epcs |= {epc}
            if epc in node.set_epcs:
                features |= ClimateEntityFeature.PRESET_MODE
                self_._attr_preset_modes = [PRESET_HOME, PRESET_AWAY]

        self_._attr_supported_features = features

    @property
    def fan_mode(self) -> str | None:
        """Return the vendor label for the current fan mode."""
        key = super().fan_mode  # type: ignore[misc]
        quirk = self._climate_quirk
        if key is None or quirk is None or not quirk.fan_mode_labels:
            return key
        if quirk.strict_fan_modes:
            return self._fan_key_to_label.get(key)
        return self._fan_key_to_label.get(key, key)

    @property
    def target_humidity(self) -> float | None:
        """Return the configured target humidity for matching devices."""
        if self._target_humidity_prop is None:
            return super().target_humidity  # type: ignore[misc]
        value = self._target_humidity_prop.get(self._node)  # type: ignore[attr-defined]
        return float(value) if value is not None else None

    @property
    def preset_mode(self) -> str | None:
        """Map the power-saving flag to standard Home/Away presets."""
        if self._power_saving_prop is None:
            return super().preset_mode  # type: ignore[misc]
        enabled = self._power_saving_prop.get(self._node)  # type: ignore[attr-defined]
        if enabled is None:
            return None
        return PRESET_AWAY if enabled else PRESET_HOME

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Translate a vendor label back to the protocol fan-mode key."""
        quirk = self._climate_quirk
        if quirk is None or not quirk.fan_mode_labels:
            await super().async_set_fan_mode(fan_mode)  # type: ignore[misc]
            return
        if quirk.strict_fan_modes:
            protocol_key = self._fan_label_to_key.get(fan_mode)
        else:
            protocol_key = self._fan_label_to_key.get(fan_mode, fan_mode)
        if protocol_key is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={"value": fan_mode},
            )
        await super().async_set_fan_mode(protocol_key)  # type: ignore[misc]

    async def async_set_humidity(self, humidity: int) -> None:
        """Set target humidity through the configured vendor EPC."""
        epc = (
            None
            if self._climate_quirk is None
            else self._climate_quirk.target_humidity_epc
        )
        if self._target_humidity_prop is None or epc not in self._node.set_epcs:  # type: ignore[attr-defined]
            raise _not_writable(epc)
        await self._send_prop(self._target_humidity_prop, float(humidity))  # type: ignore[attr-defined]

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set Home/Away by toggling power-saving operation."""
        if preset_mode not in {PRESET_HOME, PRESET_AWAY}:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={"value": preset_mode},
            )
        epc = (
            None
            if self._climate_quirk is None
            else self._climate_quirk.power_saving_preset_epc
        )
        if self._power_saving_prop is None or epc not in self._node.set_epcs:  # type: ignore[attr-defined]
            raise _not_writable(epc)
        await self._send_prop(self._power_saving_prop, preset_mode == PRESET_AWAY)  # type: ignore[attr-defined]
