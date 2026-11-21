"""Validate local platforms against Home Assistant and pyhems without device access."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio, importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from homeassistant.exceptions import ServiceValidationError
from pyhems import NodeState, EOJ
from custom_components.echonet_lite import (
    catalog,
    sensor,
    binary_sensor,
    climate,
    water_heater,
)
from custom_components.echonet_lite.quirks import sensor as quirk_sensors
from custom_components.echonet_lite.quirks import water_heater as quirk_water_heaters
from custom_components.echonet_lite.quirks.climate import quirk_climate
from custom_components.echonet_lite.quirks.sensor import quirk_sensor

Climate = quirk_climate(climate.EchonetLiteClimate)
Sensor = quirk_sensor(sensor.EchonetLiteSensor)
assert Climate is quirk_climate(climate.EchonetLiteClimate)  # cached subclass

for name in (
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "date",
    "datetime",
    "fan",
    "light",
    "lock",
    "number",
    "select",
    "sensor",
    "switch",
    "time",
    "water_heater",
    "runtime",
):
    importlib.import_module("custom_components.echonet_lite." + name)


def node(code, vendor, product=None, properties=None, writable=()):
    return NodeState(
        eoj=EOJ((code << 8) | 1),
        properties=properties or {},
        node_id="00112233445566778899AABBCCDDEEFF",
        manufacturer_code=vendor,
        get_epcs=frozenset((properties or {}).keys()),
        set_epcs=frozenset(writable),
        inf_epcs=frozenset(),
        poll_epcs=frozenset(),
        fast_poll_epcs=frozenset(),
        product_code=product,
        serial_number=None,
    )


def coordinator():
    return SimpleNamespace(
        device_info_cache={},
        device_manager=SimpleNamespace(
            set_properties=AsyncMock(
                return_value=SimpleNamespace(
                    sent=True, rejected_epcs=(), unanswered_epcs=()
                )
            )
        ),
    )


def description(module, n, key):
    return next(
        d
        for d in module._DESCRIPTIONS[n.eoj.class_code]
        if d.translation_key == key and d.should_create(n)
    )


# The catalog and monitor selection must include the local push notification EPC.
v = node(0x0008, 0x00002F, "WP-2MED", {0xB1: b"\x41"})
d = description(binary_sensor, v, "quirk_aiphone_visitor_call")
assert d.prop.get(v) is True
assert 0xB1 in catalog.monitored_epcs_for(0x0008, 0x00002F)
assert not d.should_create(node(0x0008, 0x00002F, "OTHER", {0xB1: b"\x41"}))
print("AIPHONE: profile matching, binary state and monitoring pass")

# Panasonic consumption units and counters must survive the new Quantity API.
p = node(
    0x027C, 0x00000B, "FC-70JR13T", {0xF2: b"\x00\x01", 0xF6: bytes.fromhex("001edc15")}
)
d = description(sensor, p, "quirk_panasonic_enefarm_f2")
assert d.device_class.value == "water" and d.state_class.value == "total"
assert d.prop.get(p) == 1
d = description(sensor, p, "quirk_panasonic_enefarm_f6")
assert d.device_class.value == "energy" and d.native_unit_of_measurement == "MJ"
assert (
    d.state_class.value == "total_increasing" and abs(d.prop.get(p) - 2022.421) < 1e-9
)
print("Ene-Farm: local sensor catalog, units and counters pass")

# Daily counters start a new last_reset cycle only on a drop after midnight.
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

dt_util.set_default_time_zone(ZoneInfo("Asia/Tokyo"))
Sensor = quirk_sensor(sensor.EchonetLiteSensor)
s = Sensor(coordinator(), p, description(sensor, p, "quirk_panasonic_enefarm_f2"))
assert s._daily_reset
tz = ZoneInfo("Asia/Tokyo")
day = datetime(2026, 11, 21, tzinfo=tz)
s._advance_cycle(4, day + timedelta(hours=10))
assert s._cycle_start == day
s._advance_cycle(3, day + timedelta(hours=10, minutes=4))  # transient dip
assert s._cycle_start == day
s._advance_cycle(87, day + timedelta(hours=23, minutes=50))
s._advance_cycle(87, day + timedelta(days=1, minutes=1))  # not cleared yet
assert s._cycle_start == day
s._advance_cycle(0, day + timedelta(days=1, minutes=2))
assert s._cycle_start == day + timedelta(days=1)
s._advance_cycle(5, day + timedelta(days=1, hours=1))
s._advance_cycle(0, day + timedelta(days=1, hours=23, minutes=55))  # early clear
assert s._cycle_start == day + timedelta(days=2)
f6 = Sensor(coordinator(), p, description(sensor, p, "quirk_panasonic_enefarm_f6"))
assert not f6._daily_reset
print("Ene-Farm: daily counter last_reset cycles pass")

# The aggregate water heater suppresses the replaced generic temperature sensor.
n = node(0x0272, 0x00000B, properties={0xE1: b"\x26", 0xE3: b"\x41"}, writable={0xE3})
c = coordinator()
h = quirk_water_heaters.build_quirk_water_heaters(c, n)[0]
assert h.current_operation == "bath_auto" and h.native_target_temperature == 38
assert not any(
    d.should_create(n)
    for d in sensor._DESCRIPTIONS[0x0272]
    if d.epc == 0xE1 and d.translation_key != "quirk_panasonic_bath_temperature"
)
asyncio.run(h.async_turn_off())
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x42"
print("Panasonic bath: aggregate entity, temperature, suppression and write pass")

# Toshiba controls must call the renamed write API and retain label mappings.
n = node(
    0x0130,
    0x000069,
    properties={
        0x80: b"\x30",
        0xA0: b"\x32",
        0xB0: b"\x42",
        0xB3: b"\x19",
        0xB4: b"\x32",
        0x8F: b"\x41",
    },
    writable={0xA0, 0xB4, 0x8F},
)
c = coordinator()
a = Climate(c, n, climate._DESCRIPTIONS[0x0130])
assert a.translation_key == "toshiba_climate"
assert a.fan_modes == ["auto", "low", "middle", "medium", "high", "powerful"]
assert a.target_humidity == 50 and a.fan_mode == "low"
asyncio.run(a.async_set_fan_mode("low"))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x32"
n_unmapped = node(
    0x0130,
    0x000069,
    properties={0x80: b"\x30", 0xA0: b"\x31", 0xB0: b"\x42"},
    writable={0xA0},
)
a_unmapped = Climate(c, n_unmapped, climate._DESCRIPTIONS[0x0130])
assert a_unmapped.fan_mode is None
for invalid_mode in ("level_1", "silent"):
    try:
        asyncio.run(a.async_set_fan_mode(invalid_mode))
    except ServiceValidationError:
        pass
    else:
        raise AssertionError(f"Expected ServiceValidationError for {invalid_mode!r}")
a_generic = Climate(
    c,
    node(0x0130, 0x000000, properties={0x80: b"\x30", 0xA0: b"\x31"}, writable={0xA0}),
    climate._DESCRIPTIONS[0x0130],
)
assert a_generic.translation_key == "climate" and a_generic.fan_mode == "level_1"
asyncio.run(a.async_set_humidity(55))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x37"
asyncio.run(a.async_set_preset_mode("away"))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].epc == 0x8F
print("Toshiba: fan labels, humidity, presets and write API pass")

# Sensor entities must read description.epc for suppression and raw EDT attributes.
n_off = node(0x0130, 0x000069, properties={0x80: b"\x31", 0xB0: b"\x42", 0xBE: b"\x14"})
n_cool = node(
    0x0130, 0x000069, properties={0x80: b"\x30", 0xB0: b"\x42", 0xBE: b"\x14"}
)
be_desc = description(sensor, n_cool, "class_0130_epc_be")
assert Sensor(c, n_off, be_desc).native_value is None
assert Sensor(c, n_cool, be_desc).native_value == 20
n_raw = node(0x027C, 0x00000B, "FC-70JR13T", {0xF9: b"\x2a"})
raw_desc = next(
    desc
    for desc in quirk_sensors._RAW_DESCRIPTIONS[0x027C]
    if desc.translation_key == "quirk_panasonic_enefarm_f9_raw"
    and desc.should_create(n_raw)
)
raw_entity = quirk_sensors.EchonetLiteRawSensor(c, n_raw, raw_desc)
assert raw_entity.native_value == "0x2A"
assert raw_entity.extra_state_attributes == {
    "raw_length": 1,
    "raw_unsigned": 42,
    "expected_length": 1,
    "length_matches": True,
}
n_raw_missing = node(0x027C, 0x00000B, "FC-70JR13T", {})
raw_missing = quirk_sensors.EchonetLiteRawSensor(c, n_raw_missing, raw_desc)
assert raw_missing.native_value is None and raw_missing.extra_state_attributes == {}
print("Sensors: suppression and raw diagnostic attributes pass")

# Floor-heater switches hold the requested state while the device settles.
from unittest.mock import patch

from custom_components.echonet_lite import switch
from custom_components.echonet_lite.quirks.switch import quirk_switch

n = node(0x0F70, 0x00000B, properties={0x80: b"\x31"}, writable={0x80})
sw = quirk_switch(switch.EchonetLiteSwitch)(
    c, n, description(switch, n, "quirk_panasonic_floor_power")
)
sw.async_write_ha_state = lambda: None
assert sw._settle_seconds == 20 and sw.is_on is False
with patch(
    "custom_components.echonet_lite.quirks.switch.async_call_later",
    return_value=lambda: None,
) as call_later:
    asyncio.run(sw.async_turn_on())
assert call_later.call_args.args[1] == 20 and sw.is_on is True
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x30"
sw._clear_pending_state(None)
assert sw.is_on is False
print("Floor heater: optimistic settle window pass")
from importlib.metadata import version

print(
    "All integration platforms imported under Home Assistant "
    f"{version('homeassistant')} and pyhems {version('pyhems')}"
)
