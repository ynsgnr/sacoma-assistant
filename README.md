# SACOMA Assistant

A [Home Assistant](https://www.home-assistant.io/) integration for the **SACOMA Ultra**
8-electrode body-composition smart scale (ICOMON / Chipsea hardware, the scale the
*Fitdays* app talks to).

It listens over Bluetooth for the scale to wake up when you step on it, reads the
measurement, and exposes weight plus the full body composition (BMI, body-fat %, muscle,
water, BMR, …) as Home Assistant sensors — **fully local, no cloud, no Fitdays account.**

> **Status: scaffolding / work in progress.** The decoding and body-composition maths live
> in the separate [`sacoma`](https://github.com/ynsgnr/sacoma-lib) library, which is still
> being finished (the WLA25 algorithm and command encoding are in progress). This repo is
> the Home Assistant wiring around it; weight and impedance work today, and the rest of the
> sensors light up as the library lands them.

## Supported devices

- [SACOMA oplaadbaar 8-sensoren personenweegschaal (8-electrode body-analysis scale with handle)](https://www.bol.com/nl/nl/p/sacoma-oplaadbaar-8-sensoren-personenweegschaal-28x-lichaamsanalyse-slimme-weegschaal-met-handvat-vetpercentage-digitaal-met-app-usb/9300000188113948/)

## How it works

The scale exposes a single proprietary BLE service (`FFB0`) with three characteristics:

| Characteristic | Direction | Purpose |
| -------------- | --------- | ------- |
| `FFB1` | app → scale | commands |
| `FFB2` | scale → app | live weight stream (A2 frames) |
| `FFB3` | scale → app | final BIA result (A3 frame: weight + 10 segmental impedances) |

```
  scale ──FFB2/FFB3 notify──▶ session ──raw bytes──▶ sacoma.protocol (decode) ─▶ sacoma.calculations (WLA25) ─▶ sensors
  scale ◀──FFB1 write──────── session ◀─cmd bytes─── sacoma.encoder      (optional, experimental)
```

The scale pushes its measurements to any connected client: once the integration connects
and subscribes to `FFB2`/`FFB3`, the live weight stream and the final result (weight + 10
segmental impedances) arrive on their own — no writes required.

The scale measures only weight and impedance, so two things happen on the integration side:

- **Auto-selection** — the scale doesn't know who is standing on it, so each configured user
  carries a weight range, and the measured weight picks the matching person (first range
  wins), exactly like the library's reference runner.
- **Body composition** — that user's **height, age and sex** turn the impedance into body-fat
  %, muscle, water, BMR and the rest (`sacoma.compute`, the WLA25 algorithm).

Each user gets their own device and sensor set, so household members' readings stay separate.

Optionally, the integration can replay the Fitdays app's `FFB1` sync (built by
`sacoma.encoder`) to make the scale show body composition on its own display: a sustained
`BA` profile heartbeat carrying the selected user, a one-time `BB`/`BD` user sync, and `B0`
acks of the scale's control frames. It's off by default and not needed to read the
measurement — enable "Show body composition on the scale's own display" in the options.

The boundary is deliberate: the **library** owns protocol (`sacoma.Session`) and the
body-composition maths (`sacoma.compute`) and does no I/O; the **integration** owns BLE and
user selection. One BLE conversation — read → select the user → optionally drive — lives in
[`session.py`](custom_components/sacoma_scale/session.py); the coordinator connects on
advertisement, calls `sacoma.compute`, and publishes per-user state
([`coordinator.py`](custom_components/sacoma_scale/coordinator.py)).

## Installation

### HACS (recommended)

1. In HACS → Integrations → ⋮ → *Custom repositories*, add
   `https://github.com/ynsgnr/sacoma-assistant` as an *Integration*.
2. Install **SACOMA Smart Scale** and restart Home Assistant.

### Manual

Copy `custom_components/sacoma_scale` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

1. Make sure Home Assistant's [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/)
   is set up and an adapter is in range of the scale.
2. Step on the scale to wake it (it only advertises while in use). It should be
   auto-discovered; otherwise add **SACOMA Smart Scale** from *Settings → Devices &
   Services → Add Integration*.
3. Name the scale.
4. Add each person who uses it: a name, a **weight range** (used to auto-select them), and
   their height, age, sex and athlete mode. Tick *Add another user* to add more.

Edit the name and users later under the integration's options (the options flow re-collects
the full user list). Discovery matches the FFB0 service UUID or the advertised name
`MY_SCALE`. The advertised name is customisable in the Fitdays app — if yours differs and the
service UUID isn't advertised, use *Add Integration* and pick the device from the list.

After setup there's no polling: the integration sleeps until the scale advertises (you step
on it), then connects, reads, and publishes — so nothing runs between weigh-ins.

## Sensors

Each configured user gets their own device with this sensor set: `weight`, `impedance`,
`bmi`, `body_fat`, `subcutaneous_fat`, `visceral_fat`, `muscle`, `skeletal_muscle`,
`body_water`, `protein`, `bone_mass`, `bmr`, `metabolic_age`, `body_score`, `whr`. A user's
sensors update only when a weigh-in falls in their weight range. `weight` is always set once
a reading lands; the body-composition sensors fill in when `sacoma` can compute them.

## Development

```bash
pip install -e ".[dev]"
pip install -e ../sacoma-lib      # the decode/compute library (until published to PyPI)
pytest
```

`tests/test_manifest.py` runs standalone; the decode-pipeline tests need the `sacoma`
library importable; full flow tests use `pytest-homeassistant-custom-component`.

## License

MIT
