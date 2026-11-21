#!/usr/bin/env python3
"""Build the fork's translation strings and merge them into an integration copy.

Upstream owns ``strings.json`` and ``translations/*.json``; the fork never edits
them in the repository. Its own strings come from two places:

- ``quirks/devices.json``: names of quirk entities, enum states, devices,
  climate fan modes and water-heater operations (``name_en``/``name_ja``/
  ``name_zh`` style fields), so each name is written exactly once;
- ``quirks/translations/<lang>.json``: other fork strings in Home Assistant's
  translation layout (for example Chinese names for upstream entities).

``scripts/fork_build.py`` applies them to the release archive. For a local
checkout run ``python scripts/quirk_translations.py --write`` (and do not
commit the resulting changes to upstream files).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "echonet_lite"
LANGUAGES = {"en": "en", "ja": "ja", "zh-Hans": "zh"}
_BINARY_STATES = {"true": "on", "false": "off"}


def _names(raw: dict[str, Any], prefix: str, where: str) -> dict[str, str]:
    """Return {language: text} for ``<prefix>_en``/``_ja``/``_zh`` fields."""
    names: dict[str, str] = {}
    for language, suffix in LANGUAGES.items():
        text = raw.get(f"{prefix}_{suffix}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{where}: missing {prefix}_{suffix}")
        names[language] = text
    return names


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = json.loads(json.dumps(value))
    return target


def _set(tree: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
    tree[path[-1]] = value


def _entity_platforms(raw: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Return platforms that may host the entity and the state-key mapping."""
    writable = raw.get("set", "notApplicable") != "notApplicable"
    if raw["type"] != "enum":
        return (["number", "sensor"] if writable else ["sensor"]), {}
    keys = {str(value["key"]) for value in raw["values"]}
    if keys == set(_BINARY_STATES):
        platforms = ["switch"] if writable else ["binary_sensor", "sensor"]
        return platforms, _BINARY_STATES
    return (["select"] if writable else ["sensor"]), {}


def quirk_fragments(devices: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build per-language translation fragments from ``devices.json``."""
    out: dict[str, dict[str, Any]] = {language: {} for language in LANGUAGES}

    def put(path: tuple[str, ...], names: dict[str, str]) -> None:
        for language, text in names.items():
            _set(out[language], path, text)

    for profile in devices["profiles"]:
        profile_id = profile["id"]
        if key := profile.get("device_translation_key"):
            put(("device", key, "name"), _names(profile, "device_name", profile_id))

        for raw in profile.get("entities", []):
            entity_id = raw["id"]
            platforms, state_keys = _entity_platforms(raw)
            names = _names(raw, "name", entity_id)
            for platform in platforms:
                put(("entity", platform, entity_id, "name"), names)
                for value in raw.get("values", []):
                    state = state_keys.get(str(value["key"]), str(value["key"]))
                    put(
                        ("entity", platform, entity_id, "state", state),
                        _names(value, "name", f"{entity_id} {value['key']}"),
                    )

        behaviors = profile.get("behaviors", {})
        if (climate := behaviors.get("climate")) and (
            key := climate.get("translation_key")
        ):
            for label in climate.get("fan_mode_labels", []):
                put(
                    (
                        "entity",
                        "climate",
                        key,
                        "state_attributes",
                        "fan_mode",
                        "state",
                        str(label["label"]),
                    ),
                    _names(label, "name", f"{key} {label['label']}"),
                )
        if heater := behaviors.get("water_heater"):
            key = heater["translation_key"]
            put(("entity", "water_heater", key, "name"), _names(heater, "name", key))
            modes = ("entity", "water_heater", key, "state_attributes")
            modes += ("operation_mode", "state")
            put(
                (*modes, str(heater.get("operation_on_key", "bath_auto"))),
                _names(heater, "operation_on_name", key),
            )
            put((*modes, "off"), _names(heater, "operation_off_name", key))
    return out


def fork_fragments(integration: Path = INTEGRATION) -> dict[str, dict[str, Any]]:
    """Return every fork translation fragment, keyed by language."""
    devices = json.loads(
        (integration / "quirks" / "devices.json").read_text(encoding="utf-8")
    )
    fragments: dict[str, dict[str, Any]] = {}
    for language, fragment in quirk_fragments(devices).items():
        overlay_path = integration / "quirks" / "translations" / f"{language}.json"
        overlay = (
            json.loads(overlay_path.read_text(encoding="utf-8"))
            if overlay_path.exists()
            else {}
        )
        fragments[language] = _deep_merge(overlay, fragment)
    return fragments


def merged_translations(
    integration: Path = INTEGRATION, source: Path = INTEGRATION
) -> dict[str, dict[str, Any]]:
    """Return ``integration``'s translations with the fork fragments applied.

    Fork strings are read from ``source``. Keys are file paths relative to the
    integration directory.
    """
    result: dict[str, dict[str, Any]] = {}
    fragments = fork_fragments(source)
    for language, fragment in fragments.items():
        path = integration / "translations" / f"{language}.json"
        base = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        result[f"translations/{language}.json"] = _deep_merge(base, fragment)
    strings = json.loads((integration / "strings.json").read_text(encoding="utf-8"))
    result["strings.json"] = _deep_merge(strings, fragments["en"])
    return result


def write(integration: Path, source: Path = INTEGRATION) -> None:
    """Merge the fork strings from ``source`` into ``integration``."""
    for relative, data in merged_translations(integration, source).items():
        indent = 4 if relative == "translations/en.json" else 2
        (integration / relative).write_text(
            json.dumps(data, indent=indent, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        metavar="DIR",
        nargs="?",
        const=str(INTEGRATION),
        help="merge into this integration directory (default: the checkout)",
    )
    args = parser.parse_args()
    if args.write is None:
        print(json.dumps(fork_fragments(), indent=2, ensure_ascii=False))
        return
    write(Path(args.write))


if __name__ == "__main__":
    main()
