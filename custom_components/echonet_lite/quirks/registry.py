"""Load and expose declarative, integration-local ECHONET Lite quirks.

The upstream pyhems registry remains authoritative.  Local definitions are
fallbacks unless a profile explicitly marks an entity as an instance-specific
replacement.  Keeping matching and protocol metadata in JSON makes the fork's
delta small and avoids patching pyhems' generated registry at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from pyhems import (
    REGISTRY,
    EntityDefinition,
    EnumValue,
    NodeState,
    PropertyRole,
)


_DEFINITIONS_PATH: Final = Path(__file__).with_name("devices.json")
_ACCESS_VALUES: Final = frozenset(
    {"required", "required_c", "required_o", "optional", "notApplicable"}
)
_NUMERIC_FORMATS: Final = frozenset(
    {"uint8", "int8", "uint16", "int16", "uint32", "int32"}
)
_STATE_CLASSES: Final = frozenset(
    {"measurement", "measurement_angle", "total", "total_increasing"}
)


def _code(value: int | str, *, maximum: int, field: str) -> int:
    """Parse and range-check an integer or hexadecimal string."""
    parsed = int(value, 0) if isinstance(value, str) else value
    if isinstance(parsed, bool) or not 0 <= parsed <= maximum:
        raise ValueError(f"{field} must be between 0 and 0x{maximum:X}")
    return parsed


def _access(value: str, *, field: str) -> str:
    """Validate an ECHONET Lite access-rule string."""
    if value not in _ACCESS_VALUES:
        raise ValueError(f"{field} has invalid access rule {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class QuirkMatch:
    """Conditions selecting a quirk profile for a discovered node."""

    class_code: int
    manufacturer_code: int | None = None
    product_codes: frozenset[str] = frozenset()

    def matches(self, node: NodeState) -> bool:
        """Return whether this selector applies to ``node``."""
        if node.eoj.class_code != self.class_code:
            return False
        if (
            self.manufacturer_code is not None
            and node.manufacturer_code != self.manufacturer_code
        ):
            return False
        if self.product_codes:
            product_code = (node.product_code or "").strip()
            return product_code in self.product_codes
        return True


@dataclass(frozen=True, slots=True)
class QuirkEntityMetadata:
    """Integration-only metadata attached to a local entity definition."""

    profile_id: str
    state_class: str | None = None
    settle_seconds: float = 0.0
    replace_upstream: bool = False


@dataclass(frozen=True, slots=True)
class RawSensorDefinition:
    """Read-only diagnostic sensor that exposes EDT as hexadecimal text."""

    id: str
    epc: int
    profile_id: str
    expected_length: int | None = None
    fallback_only: bool = True


@dataclass(frozen=True, slots=True)
class ValueCondition:
    """One raw EDT condition used by a value-suppression rule."""

    epc: int
    equals: bytes


@dataclass(frozen=True, slots=True)
class ValueSuppressionRule:
    """Return no state for a target EPC while any raw condition is true."""

    target_epc: int
    dependencies: frozenset[int]
    when_any: tuple[ValueCondition, ...]


@dataclass(frozen=True, slots=True)
class ClimateQuirk:
    """Optional climate-platform adaptations supplied by one profile."""

    profile_id: str
    target_humidity_epc: int | None = None
    power_saving_preset_epc: int | None = None
    fan_mode_labels: tuple[tuple[str, str], ...] = ()

    @property
    def fan_key_to_label(self) -> dict[str, str]:
        """Return protocol enum key to Home Assistant label mapping."""
        return dict(self.fan_mode_labels)


@dataclass(frozen=True, slots=True)
class WaterHeaterQuirk:
    """Description for a quirk-provided water-heater aggregate entity."""

    profile_id: str
    translation_key: str
    operation_epc: int
    operation_on_edt: int
    operation_off_edt: int
    temperature_epc: int | None = None
    operation_on_key: str = "bath_auto"


@dataclass(frozen=True, slots=True)
class QuirkProfile:
    """One complete, declaratively configured device profile."""

    id: str
    match: QuirkMatch
    verified: bool
    device_translation_key: str | None
    entity_definitions: tuple[EntityDefinition, ...]
    raw_sensors: tuple[RawSensorDefinition, ...]
    claimed_epcs: frozenset[int]
    suppression_rules: tuple[ValueSuppressionRule, ...]
    climate: ClimateQuirk | None
    water_heater: WaterHeaterQuirk | None


class QuirkRegistry:
    """Validated collection of local profiles and upstream fallback definitions."""

    def __init__(
        self,
        profiles: tuple[QuirkProfile, ...],
        entity_metadata: Mapping[str, QuirkEntityMetadata],
    ) -> None:
        """Initialize indexes used by platform setup and runtime matching."""
        self.profiles = profiles
        self._profiles_by_id = MappingProxyType({p.id: p for p in profiles})
        self._entity_metadata = MappingProxyType(dict(entity_metadata))
        self._local_entity_ids = frozenset(entity_metadata)

        merged: dict[int, list[EntityDefinition]] = {
            class_code: list(entity_defs)
            for class_code, entity_defs in REGISTRY.entities.items()
        }
        upstream_epcs: dict[int, frozenset[int]] = {
            class_code: frozenset(entity.epc for entity in entity_defs)
            for class_code, entity_defs in REGISTRY.entities.items()
        }
        for profile in profiles:
            target = merged.setdefault(profile.match.class_code, [])
            existing_epcs = upstream_epcs.get(profile.match.class_code, frozenset())
            for entity_def in profile.entity_definitions:
                metadata = self._entity_metadata[entity_def.id]
                if entity_def.epc in existing_epcs and not metadata.replace_upstream:
                    continue
                target.append(entity_def)
        self.entities = MappingProxyType(
            {class_code: tuple(values) for class_code, values in merged.items()}
        )

        raw_by_class: dict[int, list[RawSensorDefinition]] = {}
        for profile in profiles:
            existing_epcs = upstream_epcs.get(profile.match.class_code, frozenset())
            for raw_sensor in profile.raw_sensors:
                if raw_sensor.fallback_only and raw_sensor.epc in existing_epcs:
                    continue
                raw_by_class.setdefault(profile.match.class_code, []).append(raw_sensor)
        self.raw_sensors = MappingProxyType(
            {class_code: tuple(values) for class_code, values in raw_by_class.items()}
        )

        monitored: dict[int, set[int]] = {}
        for profile in profiles:
            epcs = monitored.setdefault(profile.match.class_code, set())
            epcs.update(entity.epc for entity in profile.entity_definitions)
            epcs.update(sensor.epc for sensor in profile.raw_sensors)
            for rule in profile.suppression_rules:
                epcs.add(rule.target_epc)
                epcs.update(rule.dependencies)
            if profile.climate is not None:
                if profile.climate.target_humidity_epc is not None:
                    epcs.add(profile.climate.target_humidity_epc)
                if profile.climate.power_saving_preset_epc is not None:
                    epcs.add(profile.climate.power_saving_preset_epc)
            if profile.water_heater is not None:
                epcs.add(profile.water_heater.operation_epc)
                if profile.water_heater.temperature_epc is not None:
                    epcs.add(profile.water_heater.temperature_epc)
        self.monitored_epcs = MappingProxyType(
            {class_code: frozenset(epcs) for class_code, epcs in monitored.items()}
        )
        self.verified_class_codes = frozenset(
            profile.match.class_code for profile in profiles if profile.verified
        )

    @classmethod
    def from_file(cls, path: Path) -> QuirkRegistry:
        """Load and validate a registry from a JSON definition file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported quirk schema_version")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("quirks profiles must be a list")

        profiles: list[QuirkProfile] = []
        metadata: dict[str, QuirkEntityMetadata] = {}
        profile_ids: set[str] = set()
        entity_ids: set[str] = set()
        for raw_profile in raw_profiles:
            profile, profile_metadata = cls._parse_profile(raw_profile)
            if profile.id in profile_ids:
                raise ValueError(f"Duplicate quirk profile id {profile.id!r}")
            profile_ids.add(profile.id)
            profile_entity_ids = {
                entity.id for entity in profile.entity_definitions
            } | {sensor.id for sensor in profile.raw_sensors}
            for entity_id in profile_entity_ids:
                if entity_id in entity_ids:
                    raise ValueError(f"Duplicate quirk entity id {entity_id!r}")
                entity_ids.add(entity_id)
            metadata.update(profile_metadata)
            profiles.append(profile)
        return cls(tuple(profiles), metadata)

    @classmethod
    def _parse_profile(
        cls, raw: Mapping[str, Any]
    ) -> tuple[QuirkProfile, dict[str, QuirkEntityMetadata]]:
        """Parse one profile and its local entity metadata."""
        profile_id = str(raw["id"])
        raw_match = raw["match"]
        match = QuirkMatch(
            class_code=_code(
                raw_match["class_code"], maximum=0xFFFF, field="class_code"
            ),
            manufacturer_code=(
                _code(
                    raw_match["manufacturer_code"],
                    maximum=0xFFFFFF,
                    field="manufacturer_code",
                )
                if "manufacturer_code" in raw_match
                else None
            ),
            product_codes=frozenset(
                str(value).strip() for value in raw_match.get("product_codes", [])
            ),
        )

        entity_defs: list[EntityDefinition] = []
        raw_sensors: list[RawSensorDefinition] = []
        metadata: dict[str, QuirkEntityMetadata] = {}
        replacement_epcs: set[int] = set()
        for raw_entity in raw.get("entities", []):
            entity_id = str(raw_entity["id"])
            if entity_id in metadata or any(
                sensor.id == entity_id for sensor in raw_sensors
            ):
                raise ValueError(
                    f"Duplicate entity id {entity_id!r} in profile {profile_id!r}"
                )
            epc = _code(raw_entity["epc"], maximum=0xFF, field="epc")
            kind = raw_entity["type"]
            replace_upstream = bool(raw_entity.get("replace_upstream", False))
            if kind == "raw":
                expected_length = raw_entity.get("expected_length")
                if expected_length is not None:
                    expected_length = _code(
                        expected_length,
                        maximum=0xFF,
                        field="expected_length",
                    )
                raw_sensors.append(
                    RawSensorDefinition(
                        id=entity_id,
                        epc=epc,
                        profile_id=profile_id,
                        expected_length=expected_length,
                        fallback_only=bool(raw_entity.get("fallback_only", True)),
                    )
                )
                continue

            definition = cls._parse_entity_definition(raw_entity, match)
            entity_defs.append(definition)
            state_class = raw_entity.get("state_class")
            if state_class is not None and state_class not in _STATE_CLASSES:
                raise ValueError(f"Unsupported state_class {state_class!r}")
            settle_seconds = float(raw_entity.get("settle_seconds", 0.0))
            if settle_seconds < 0:
                raise ValueError("settle_seconds cannot be negative")
            metadata[entity_id] = QuirkEntityMetadata(
                profile_id=profile_id,
                state_class=state_class,
                settle_seconds=settle_seconds,
                replace_upstream=replace_upstream,
            )
            if replace_upstream:
                replacement_epcs.add(epc)

        behaviors = raw.get("behaviors", {})
        claimed_epcs = {
            _code(value, maximum=0xFF, field="claimed_epcs")
            for value in behaviors.get("claimed_epcs", [])
        }
        claimed_epcs.update(replacement_epcs)

        suppression_rules = tuple(
            cls._parse_suppression_rule(rule)
            for rule in behaviors.get("suppress_values", [])
        )
        climate = cls._parse_climate(profile_id, behaviors.get("climate"))
        water_heater = cls._parse_water_heater(
            profile_id, behaviors.get("water_heater")
        )
        if (
            water_heater is not None
            and water_heater.temperature_epc is not None
            and not any(
                entity.epc == water_heater.temperature_epc for entity in entity_defs
            )
        ):
            raise ValueError(
                f"Water-heater profile {profile_id!r} has no local definition "
                f"for temperature EPC 0x{water_heater.temperature_epc:02X}"
            )
        return (
            QuirkProfile(
                id=profile_id,
                match=match,
                verified=bool(raw.get("verified", False)),
                device_translation_key=raw.get("device_translation_key"),
                entity_definitions=tuple(entity_defs),
                raw_sensors=tuple(raw_sensors),
                claimed_epcs=frozenset(claimed_epcs),
                suppression_rules=suppression_rules,
                climate=climate,
                water_heater=water_heater,
            ),
            metadata,
        )

    @staticmethod
    def _parse_entity_definition(
        raw: Mapping[str, Any], match: QuirkMatch
    ) -> EntityDefinition:
        """Convert a numeric or enum JSON entry to a pyhems definition."""
        kind = raw["type"]
        if kind not in {"numeric", "enum"}:
            raise ValueError(f"Unsupported quirk entity type {kind!r}")
        get_access = _access(raw.get("get", "optional"), field="get")
        set_access = _access(raw.get("set", "notApplicable"), field="set")
        enum_values: tuple[EnumValue, ...] = ()
        mra_format: str | None = None
        if kind == "numeric":
            mra_format = raw["format"]
            if mra_format not in _NUMERIC_FORMATS:
                raise ValueError(f"Unsupported numeric format {mra_format!r}")
        else:
            enum_values = tuple(
                EnumValue(
                    edt=_code(value["edt"], maximum=0xFF, field="enum edt"),
                    key=str(value["key"]),
                    name_en=str(value["name_en"]),
                    name_ja=str(value["name_ja"]),
                )
                for value in raw["values"]
            )
        return EntityDefinition(
            id=str(raw["id"]),
            epc=_code(raw["epc"], maximum=0xFF, field="epc"),
            name_en=str(raw["name_en"]),
            name_ja=str(raw["name_ja"]),
            get=get_access,
            set=set_access,
            format=mra_format,
            unit=raw.get("unit"),
            minimum=raw.get("minimum"),
            maximum=raw.get("maximum"),
            multiple_of=float(raw.get("scale", 1.0)),
            enum_values=enum_values,
            manufacturer_code=match.manufacturer_code,
            role=PropertyRole(raw.get("role", "primary")),
        )

    @staticmethod
    def _parse_suppression_rule(raw: Mapping[str, Any]) -> ValueSuppressionRule:
        """Parse a declarative sensor-state suppression rule."""
        conditions = tuple(
            ValueCondition(
                epc=_code(value["epc"], maximum=0xFF, field="condition epc"),
                equals=bytes.fromhex(str(value["equals_hex"])),
            )
            for value in raw["when_any"]
        )
        if not conditions:
            raise ValueError("suppress_values when_any cannot be empty")
        dependencies = {
            _code(value, maximum=0xFF, field="dependency epc")
            for value in raw.get("dependencies", [])
        }
        dependencies.update(condition.epc for condition in conditions)
        return ValueSuppressionRule(
            target_epc=_code(raw["epc"], maximum=0xFF, field="target epc"),
            dependencies=frozenset(dependencies),
            when_any=conditions,
        )

    @staticmethod
    def _parse_climate(
        profile_id: str, raw: Mapping[str, Any] | None
    ) -> ClimateQuirk | None:
        """Parse optional climate adaptations."""
        if raw is None:
            return None
        labels = tuple(
            (str(value["key"]), str(value["label"]))
            for value in raw.get("fan_mode_labels", [])
        )
        if len({key for key, _label in labels}) != len(labels):
            raise ValueError("climate fan_mode_labels contains duplicate keys")
        if len({label for _key, label in labels}) != len(labels):
            raise ValueError("climate fan_mode_labels contains duplicate labels")
        return ClimateQuirk(
            profile_id=profile_id,
            target_humidity_epc=(
                _code(
                    raw["target_humidity_epc"],
                    maximum=0xFF,
                    field="target_humidity_epc",
                )
                if "target_humidity_epc" in raw
                else None
            ),
            power_saving_preset_epc=(
                _code(
                    raw["power_saving_preset_epc"],
                    maximum=0xFF,
                    field="power_saving_preset_epc",
                )
                if "power_saving_preset_epc" in raw
                else None
            ),
            fan_mode_labels=labels,
        )

    @staticmethod
    def _parse_water_heater(
        profile_id: str, raw: Mapping[str, Any] | None
    ) -> WaterHeaterQuirk | None:
        """Parse an optional water-heater aggregate description."""
        if raw is None:
            return None
        operation_on_edt = _code(
            raw["operation_on_edt"], maximum=0xFF, field="operation_on_edt"
        )
        operation_off_edt = _code(
            raw["operation_off_edt"], maximum=0xFF, field="operation_off_edt"
        )
        if operation_on_edt == operation_off_edt:
            raise ValueError("water-heater on/off EDT values must differ")
        return WaterHeaterQuirk(
            profile_id=profile_id,
            translation_key=str(raw["translation_key"]),
            operation_epc=_code(
                raw["operation_epc"], maximum=0xFF, field="operation_epc"
            ),
            operation_on_edt=operation_on_edt,
            operation_off_edt=operation_off_edt,
            temperature_epc=(
                _code(
                    raw["temperature_epc"],
                    maximum=0xFF,
                    field="temperature_epc",
                )
                if "temperature_epc" in raw
                else None
            ),
            operation_on_key=str(raw.get("operation_on_key", "bath_auto")),
        )

    def profile_matches(self, profile_id: str, node: NodeState) -> bool:
        """Return whether one named profile matches ``node``."""
        return self._profiles_by_id[profile_id].match.matches(node)

    def entity_matches(self, entity_id: str, node: NodeState) -> bool:
        """Return whether a local entity definition applies to ``node``."""
        metadata = self._entity_metadata.get(entity_id)
        return metadata is None or self.profile_matches(metadata.profile_id, node)

    def suppresses_generic_entity(
        self, node: NodeState, entity_id: str | None, epc: int
    ) -> bool:
        """Return whether a profile claims an upstream generic entity EPC."""
        if entity_id in self._local_entity_ids:
            return False
        return any(
            profile.match.matches(node) and epc in profile.claimed_epcs
            for profile in self.profiles
        )

    def sensor_state_class(self, entity_id: str) -> str | None:
        """Return an explicit HA state-class override for a local entity."""
        metadata = self._entity_metadata.get(entity_id)
        return None if metadata is None else metadata.state_class

    def local_entity_definition(
        self, profile_id: str, epc: int
    ) -> EntityDefinition | None:
        """Return one profile-local definition by EPC.

        Dedicated quirk entities use this to reuse the same declarative codec
        metadata as the standalone entity instead of duplicating byte formats
        in platform code.
        """
        profile = self._profiles_by_id[profile_id]
        return next(
            (entity for entity in profile.entity_definitions if entity.epc == epc),
            None,
        )

    def settle_seconds(self, node: NodeState, entity_id: str, epc: int) -> float:
        """Return optimistic state hold time for a matching local switch."""
        metadata = self._entity_metadata.get(entity_id)
        if metadata is None or not self.profile_matches(metadata.profile_id, node):
            return 0.0
        definition = next(
            (
                entity
                for profile in self.profiles
                if profile.id == metadata.profile_id
                for entity in profile.entity_definitions
                if entity.id == entity_id and entity.epc == epc
            ),
            None,
        )
        return metadata.settle_seconds if definition is not None else 0.0

    def dependencies_for(self, node: NodeState, epc: int) -> frozenset[int]:
        """Return extra EPCs needed to evaluate the state of ``epc``."""
        dependencies: set[int] = set()
        for profile in self.profiles:
            if not profile.match.matches(node):
                continue
            for rule in profile.suppression_rules:
                if rule.target_epc == epc:
                    dependencies.update(rule.dependencies)
        return frozenset(dependencies)

    def should_suppress_value(self, node: NodeState, epc: int) -> bool:
        """Return whether a matching declarative raw-value condition is true."""
        for profile in self.profiles:
            if not profile.match.matches(node):
                continue
            for rule in profile.suppression_rules:
                if rule.target_epc != epc:
                    continue
                if any(
                    node.properties.get(condition.epc) == condition.equals
                    for condition in rule.when_any
                ):
                    return True
        return False

    def raw_sensor_matches(self, sensor: RawSensorDefinition, node: NodeState) -> bool:
        """Return whether a raw diagnostic sensor applies to ``node``."""
        return self.profile_matches(sensor.profile_id, node)

    def climate_for(self, node: NodeState) -> ClimateQuirk | None:
        """Return the first matching climate adaptation."""
        return next(
            (
                profile.climate
                for profile in self.profiles
                if profile.climate is not None and profile.match.matches(node)
            ),
            None,
        )

    def water_heater_for(self, node: NodeState) -> WaterHeaterQuirk | None:
        """Return the first matching quirk water-heater description."""
        return next(
            (
                profile.water_heater
                for profile in self.profiles
                if profile.water_heater is not None and profile.match.matches(node)
            ),
            None,
        )

    def device_translation_key(self, node: NodeState) -> str | None:
        """Return a translated device-name key for a matching unknown class."""
        return next(
            (
                profile.device_translation_key
                for profile in self.profiles
                if profile.device_translation_key is not None
                and profile.match.matches(node)
            ),
            None,
        )


QUIRKS: Final = QuirkRegistry.from_file(_DEFINITIONS_PATH)
