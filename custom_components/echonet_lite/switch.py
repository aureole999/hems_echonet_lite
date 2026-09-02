"""Switch platform for the HEMS Echonet Lite integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from pyhems import EntityDefinition, NodeState

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .entity import (
    EchonetLiteDescribedEntity,
    EchonetLiteEntityDescription,
    build_platform_descriptions,
    setup_common_platform,
)
from .coordinator import EchonetLiteCoordinator
from .prop import BinaryProp
from .quirks import QUIRKS
from .runtime import EchonetLiteConfigEntry

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EchonetLiteSwitchEntityDescription(
    SwitchEntityDescription, EchonetLiteEntityDescription
):
    """Entity description that also stores EPC metadata."""

    prop: BinaryProp

    @classmethod
    @override
    def build_from_entity_def(
        cls,
        entity_def: EntityDefinition,
    ) -> EchonetLiteSwitchEntityDescription:
        """Construct a switch description from an EntityDefinition."""
        return cls(
            key=f"{entity_def.epc:02x}",
            prop=BinaryProp.from_entity_def(entity_def),
            **cls._common_kwargs(entity_def),
        )


_DESCRIPTIONS: dict[int, list[EchonetLiteSwitchEntityDescription]] = (
    build_platform_descriptions(Platform.SWITCH, EchonetLiteSwitchEntityDescription)
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: EchonetLiteConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ECHONET Lite switches from a config entry."""
    setup_common_platform(
        entry,
        async_add_entities,
        Platform.SWITCH.value,
        _DESCRIPTIONS,
        EchonetLiteSwitch,
    )


class EchonetLiteSwitch(
    EchonetLiteDescribedEntity[EchonetLiteSwitchEntityDescription], SwitchEntity
):
    """Representation of a writable ECHONET Lite property."""

    def __init__(
        self,
        coordinator: EchonetLiteCoordinator,
        node: NodeState,
        description: EchonetLiteSwitchEntityDescription,
    ) -> None:
        """Initialize optional quirk-configured state settling."""
        super().__init__(coordinator, node, description)
        self._settle_seconds = QUIRKS.settle_seconds(
            node, description.translation_key or "", description.epc
        )
        self._pending_state: bool | None = None
        self._cancel_settle: Callable[[], None] | None = None

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the decoded boolean value stored in the coordinator."""
        if self._pending_state is not None:
            return self._pending_state
        return self.description.prop.get(self._node)

    def _hold_pending_state(self, value: bool) -> None:
        """Keep an optimistic state while a slow device applies its command."""
        if self._settle_seconds <= 0:
            return
        if self._cancel_settle is not None:
            self._cancel_settle()
        self._pending_state = value
        self._cancel_settle = async_call_later(
            self.hass, self._settle_seconds, self._clear_pending_state
        )
        self.async_write_ha_state()

    @callback
    def _clear_pending_state(self, _now: Any) -> None:
        """Return to the device-reported state after the settling window."""
        self._cancel_settle = None
        self._pending_state = None
        self.async_write_ha_state()

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the On command via the pyhems runtime client."""
        await self._async_send_prop(self.description.prop, True)
        self._hold_pending_state(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the Off command via the pyhems runtime client."""
        await self._async_send_prop(self.description.prop, False)
        self._hold_pending_state(False)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Cancel a pending settle callback before removal."""
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None
        await super().async_will_remove_from_hass()
