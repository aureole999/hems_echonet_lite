#!/usr/bin/env python3
"""Validate integration-local quirk definitions without importing Home Assistant."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from pyhems import get_codec


ROOT = Path(__file__).resolve().parents[1]
COMPAT_PATH = ROOT / "custom_components" / "echonet_lite" / "pyhems_compat.py"
REGISTRY_PATH = ROOT / "custom_components" / "echonet_lite" / "quirks" / "registry.py"
TRANSLATION_PATHS = (
    ROOT / "custom_components" / "echonet_lite" / "strings.json",
    ROOT / "custom_components" / "echonet_lite" / "translations" / "en.json",
    ROOT / "custom_components" / "echonet_lite" / "translations" / "ja.json",
)


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a standalone module without running the integration package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _translation_keys(data: dict) -> set[str]:
    """Collect all device and entity translation keys."""
    keys = set(data.get("device", {}))
    for platform_values in data.get("entity", {}).values():
        keys.update(platform_values)
    return keys


def _validate_discovery_compat(compat: ModuleType) -> None:
    """Validate both released and development pyhems discovery surfaces."""

    class ReleasedClient:
        probe_calls = 0

        async def probe_nodes(self) -> bool:
            self.probe_calls += 1
            return True

    class DevelopmentClient(ReleasedClient):
        initial_probe_calls = 0
        periodic_start_calls = 0

        async def probe_initial_nodes(self) -> bool:
            self.initial_probe_calls += 1
            return True

        def start_periodic_discovery(self) -> None:
            self.periodic_start_calls += 1

    released = ReleasedClient()
    if not asyncio.run(compat.async_probe_initial_nodes(released)):
        raise ValueError("Released pyhems discovery compatibility probe failed")
    compat.start_periodic_discovery(released)
    if released.probe_calls != 1:
        raise ValueError("Released pyhems did not use probe_nodes exactly once")

    development = DevelopmentClient()
    if not asyncio.run(compat.async_probe_initial_nodes(development)):
        raise ValueError("Development pyhems initial discovery probe failed")
    compat.start_periodic_discovery(development)
    if development.initial_probe_calls != 1 or development.probe_calls != 0:
        raise ValueError("Development pyhems did not prefer probe_initial_nodes")
    if development.periodic_start_calls != 1:
        raise ValueError("Development pyhems periodic discovery was not started")


def main() -> None:
    """Validate schema, translations, and captured real-device decode fixtures."""
    compat = _load_module("echonet_pyhems_compat", COMPAT_PATH)
    _validate_discovery_compat(compat)
    device_class = compat.DeviceClass
    registry = _load_module("echonet_quirk_registry", REGISTRY_PATH).QUIRKS
    unknown_class_codes = {
        int(class_code) for class_code in device_class if class_code not in registry.entities
    }
    if unknown_class_codes:
        codes = ", ".join(f"0x{code:04X}" for code in sorted(unknown_class_codes))
        raise ValueError(f"Compatibility enum contains unknown class codes: {codes}")
    required_translation_keys: set[str] = set()
    for profile in registry.profiles:
        required_translation_keys.update(
            entity.id for entity in profile.entity_definitions
        )
        required_translation_keys.update(sensor.id for sensor in profile.raw_sensors)
        if profile.device_translation_key is not None:
            required_translation_keys.add(profile.device_translation_key)
        if profile.water_heater is not None:
            required_translation_keys.add(profile.water_heater.translation_key)

    for path in TRANSLATION_PATHS:
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = required_translation_keys - _translation_keys(data)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"{path}: missing translation keys: {missing_text}")

    # Captured read-only responses from Panasonic FC-70JR13T / 0x027201.
    fixtures = (
        ("panasonic_enefarm_fc_70jr13t", 0xF2, "0000", 0),
        ("panasonic_enefarm_fc_70jr13t", 0xF6, "001edc15", 20224.21),
        ("panasonic_enefarm_fc_70jr13t", 0xF7, "001721c9", 1515.977),
        ("panasonic_instantaneous_water_heater", 0xE1, "26", 38),
    )
    for profile_id, epc, edt_hex, expected in fixtures:
        definition = registry.local_entity_definition(profile_id, epc)
        if definition is None:
            raise ValueError(f"Missing fixture definition {profile_id} EPC 0x{epc:02X}")
        actual = get_codec(definition).decode(bytes.fromhex(edt_hex))
        if actual is None or abs(actual - expected) > 1e-9:
            raise ValueError(
                f"{profile_id} EPC 0x{epc:02X}: decoded {actual!r}, "
                f"expected {expected!r}"
            )

    def node(
        class_code: int,
        manufacturer_code: int,
        product_code: str | None = None,
        properties: dict[int, bytes] | None = None,
    ) -> SimpleNamespace:
        """Build the minimal NodeState-shaped object needed by match rules."""
        return SimpleNamespace(
            eoj=SimpleNamespace(class_code=class_code),
            manufacturer_code=manufacturer_code,
            product_code=product_code,
            properties=properties or {},
        )

    enefarm = node(0x027C, 0x00000B, "FC-70JR13T")
    other_fuel_cell = node(0x027C, 0x00000B, "OTHER")
    if not registry.entity_matches("quirk_panasonic_enefarm_f2", enefarm):
        raise ValueError("Ene-Farm product selector did not match FC-70JR13T")
    if registry.entity_matches("quirk_panasonic_enefarm_f2", other_fuel_cell):
        raise ValueError("Ene-Farm product selector matched an unrelated model")

    floor = node(0x0F70, 0x00000B)
    settle = registry.settle_seconds(floor, "quirk_panasonic_floor_power", 0x80)
    if settle != 20:
        raise ValueError(f"Unexpected floor-heater settling delay: {settle}")

    toshiba_off = node(0x0130, 0x000069, properties={0x80: b"\x31"})
    toshiba_fan = node(0x0130, 0x000069, properties={0xB0: b"\x45"})
    toshiba_cool = node(0x0130, 0x000069, properties={0xB0: b"\x42"})
    if not registry.should_suppress_value(toshiba_off, 0xBE):
        raise ValueError("Toshiba outdoor temperature was not suppressed while off")
    if not registry.should_suppress_value(toshiba_fan, 0xBE):
        raise ValueError("Toshiba outdoor temperature was not suppressed in fan mode")
    if registry.should_suppress_value(toshiba_cool, 0xBE):
        raise ValueError("Toshiba outdoor temperature was suppressed while cooling")

    print(
        f"Validated {len(registry.profiles)} quirk profiles and "
        f"{len(required_translation_keys)} translation keys."
    )


if __name__ == "__main__":
    main()
