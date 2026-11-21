"""Switch quirks: hold an optimistic state while a slow device applies a command."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

from .platform import with_mixin
from .registry import QUIRKS


def quirk_switch[T: type](base: T) -> T:
    """Return the switch entity class with quirk support."""
    return with_mixin(SettlingSwitchMixin, base)


class SettlingSwitchMixin:
    """Report the requested state for ``settle_seconds`` after a command.

    Some appliances keep reporting the old state for a while after accepting
    a Set request. Entities without a configured delay behave as upstream.
    """

    def __init__(self, coordinator: Any, node: Any, description: Any) -> None:
        """Initialize the upstream entity and read the configured delay."""
        super().__init__(coordinator, node, description)  # type: ignore[call-arg]
        self._settle_seconds = QUIRKS.settle_seconds(
            node, description.translation_key or "", description.epc
        )
        self._pending_state: bool | None = None
        self._cancel_settle: Callable[[], None] | None = None

    @property
    def is_on(self) -> bool | None:
        """Return the pending state while settling, else the device state."""
        if self._pending_state is not None:
            return self._pending_state
        return super().is_on  # type: ignore[misc]

    def _hold_pending_state(self, value: bool) -> None:
        if self._settle_seconds <= 0:
            return
        if self._cancel_settle is not None:
            self._cancel_settle()
        self._pending_state = value
        self_: Any = self
        self._cancel_settle = async_call_later(
            self_.hass, self._settle_seconds, self._clear_pending_state
        )
        self_.async_write_ha_state()

    @callback
    def _clear_pending_state(self, _now: Any) -> None:
        self._cancel_settle = None
        self._pending_state = None
        self_: Any = self
        self_.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send On, then hold the optimistic state."""
        await super().async_turn_on(**kwargs)  # type: ignore[misc]
        self._hold_pending_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send Off, then hold the optimistic state."""
        await super().async_turn_off(**kwargs)  # type: ignore[misc]
        self._hold_pending_state(False)

    async def async_will_remove_from_hass(self) -> None:
        """Cancel a pending settle callback before removal."""
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None
        await super().async_will_remove_from_hass()  # type: ignore[misc]
