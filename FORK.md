# About this fork

This fork of [sayurin/hems_echonet_lite](https://github.com/sayurin/hems_echonet_lite)
adds household device quirks and Chinese translations. It is laid out so that
merging upstream touches as few upstream files as possible.

## Device quirks

Profiles live in
[`custom_components/echonet_lite/quirks/devices.json`](custom_components/echonet_lite/quirks/devices.json);
see the [quirk schema notes](custom_components/echonet_lite/quirks/README.md).
The pyhems registry stays authoritative: local definitions only fill gaps and
yield automatically when pyhems defines the same EPC.

Included profiles:

- Panasonic ENE-FARM `FC-70JR13T` (0x027C): vendor properties F2, F3, F4, F6
  and F7, named after Panasonic AiSEG2's history items (for example F6 is
  燃料電池排熱回収量, 0.001 MJ), plus a raw diagnostic F9;
- Panasonic instantaneous water heater (0x0272): bath temperature, bath-auto
  control via E3, and a raw diagnostic F0;
- Panasonic floor heater (0x0F70): power with a settling delay, read-only
  heating level;
- AIPHONE WP-2MED visitor sensor (0x0008) and display (0x0601): a real-time
  visitor-call binary sensor driven by multicast INF notifications;
- Toshiba home air conditioner (0x0130): fan labels, target humidity,
  Home/Away power-saving presets, and outdoor-temperature suppression.

## What differs from upstream

| Area | Fork files | Upstream files touched |
|---|---|---|
| Quirk definitions and behavior | `quirks/` | one-line hooks in `catalog.py`, `entity.py`, `climate.py`, `sensor.py`, `switch.py`, `water_heater.py` |
| Translations | `quirks/devices.json`, `quirks/translations/` | none (merged at build time) |
| Release | `.github/workflows/fork-*.yml`, `scripts/fork_build.py` | entries in `.github/workflows/actions.lock` |
| Branding | | `name`, `codeowners` and URLs in `manifest.json`, `name` in `hacs.json` |

## Releasing

Run the **Fork release** workflow and pick patch, minor or major. It tags the
next `vX.Y.Z` after the highest existing tag and attaches
`echonet_lite.zip`. The committed manifest keeps upstream's `0.0.0`
placeholder; the version is written into the archive only.

Upstream's `release.yml` (release-please) needs a GitHub App the fork does
not have; keep it disabled in the fork's Actions settings.

## Merging upstream

```sh
git fetch upstream
git merge upstream/master
python scripts/validate_quirks.py
python scripts/validate_platforms.py
```

If `actions.lock` conflicts, keep both sides' workflow entries.

## Local checks

With Python 3.14, the manifest's pyhems pin and Home Assistant installed:

```sh
python scripts/validate_quirks.py
python scripts/validate_platforms.py
python scripts/fork_build.py --version 9999.0.0
```

To run the checkout directly in Home Assistant, first apply the fork strings
with `python scripts/quirk_translations.py --write` (do not commit that).
