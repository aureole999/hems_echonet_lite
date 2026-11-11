"""Validate local platforms against Home Assistant and pyhems without device access."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio, importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pyhems import NodeState, EOJ
from custom_components.echonet_lite import (
    catalog,
    sensor,
    binary_sensor,
    climate,
    water_heater,
)

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
assert d.device_class.value == "water" and d.state_class.value == "total_increasing"
assert d.prop.get(p) == 1
d = description(sensor, p, "quirk_panasonic_enefarm_f6")
assert (
    d.state_class.value == "total_increasing" and abs(d.prop.get(p) - 20224.21) < 1e-9
)
print("Ene-Farm: local sensor catalog, units and counters pass")

# The aggregate water heater suppresses the replaced generic temperature sensor.
n = node(0x0272, 0x00000B, properties={0xE1: b"\x26", 0xE3: b"\x41"}, writable={0xE3})
c = coordinator()
h = water_heater._build_quirk_water_heaters(c, n)[0]
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
        0xA0: b"\x31",
        0xB0: b"\x42",
        0xB3: b"\x19",
        0xB4: b"\x32",
        0x8F: b"\x41",
    },
    writable={0xA0, 0xB4, 0x8F},
)
c = coordinator()
a = climate.EchonetLiteClimate(c, n, climate._DESCRIPTIONS[0x0130])
assert a.target_humidity == 50 and a.fan_mode == "silent"
asyncio.run(a.async_set_fan_mode("silent"))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x31"
asyncio.run(a.async_set_humidity(55))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].edt == b"\x37"
asyncio.run(a.async_set_preset_mode("away"))
assert c.device_manager.set_properties.call_args.kwargs["properties"][0].epc == 0x8F
print("Toshiba: fan labels, humidity, presets and write API pass")
print(
    "All integration platforms imported under Home Assistant 2026.11.0 and pyhems 0.9.1"
)
