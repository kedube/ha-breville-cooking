# Breville+ Cooking for Home Assistant

Unofficial Home Assistant integration for appliances that use the Breville+
Cooking app, through Breville's cloud. Not affiliated with or endorsed by
Breville.

| Appliance | Model | Status |
|---|---|---|
| ChefSteps Joule Sous Vide | CSJ100 | Tested on a real appliance |
| Joule Turbo Sous Vide | BSV600 | Built from the app's code; untested |
| Joule Oven Air Fryer Pro | BOV950 | Built from the app's code; untested |

Other models on the account (espresso machines, other ovens) are ignored.
If you have a BSV600 or BOV950, please try it and open an issue with your
[diagnostics](#troubleshooting) either way.

## Installation

**HACS:** add `https://github.com/kedube/ha-breville-cooking` as a custom
repository (type *Integration*), install **Breville+ Cooking** and restart.

**Manually:** unzip `breville_cooking.zip` from the
[latest release](https://github.com/kedube/ha-breville-cooking/releases/latest)
into `config/custom_components/breville_cooking` (or copy that folder from
this repository) and restart.

Then go to **Settings → Devices & services → Add integration → Breville+
Cooking** and log in with your Breville+ account. Home Assistant keeps a login
session, not your password; if the session expires you'll be asked to log in
again. Accounts with multi-factor authentication aren't supported yet.

The appliance must be connected to Wi-Fi in the Breville+ app (a Joule set to
"Bluetooth only" can't be reached).

## What you get

Each appliance becomes a device with:

- **Status**: idle, preheating, ready for food, cooking, done, keeping warm,
  waiting for a button press, error, offline.
- **Temperature** (water or oven), **Time remaining**, **Cook end** (a
  timestamp, handy for notifications), **Cooking**, **Problem** and **Error**.
- **Target temperature** and **Cook time**: while idle, these set up the next
  cook; while cooking, changing them adjusts the running cook. For sous vide, a
  cook time of 0 holds the temperature until you stop it.
- **Cook** switch: turn on to start a cook with those settings, off to stop.
- **Continue** button: tells the appliance the food is in (starting the timer)
  or has been taken out, like the button in the app.
- **Start timer automatically**: start the timer as soon as the temperature is
  reached instead of waiting for **Continue**.
- Oven only: **Mode**, **Convection**, **Level** (broil and slow cook),
  **Keep warm**, **Door** and **Active mode**.

Changes arrive within a couple of seconds over Breville's websocket; nothing is
polled.

### Starting a cook from an automation

```yaml
action: breville_cooking.start_cook
target:
  entity_id: switch.joule_cook
data:
  temperature: 57      # in your Home Assistant unit
  duration: "01:30:00" # leave out to hold the temperature
```

For the oven, add `mode` (for example `air_fry`, `bake`, `roast`, `broil`),
and optionally `convection`, `level` and `keep_warm`. Settings you leave out
come from the appliance's entities.

### Safety

Cooks start remotely, with nobody nearby. Only start a sous vide when it's in
water, and an oven when it's empty of anything that shouldn't be heated. Like
the app, the integration follows each model's temperature and time limits.
UL-certified Joules (North America) wait for a press of their top button
before cooks above 85 °C; the oven may ask for a press of **Start**, shown as
"Press the button on the appliance".

## Troubleshooting

Download diagnostics from the device page (⋮ → **Download diagnostics**). They
contain the appliance's raw state with tokens, email and IDs removed, which is
what's needed to support a new model or firmware.

## Development

```sh
python3 -m pip install -r requirements_test.txt
python3 -m pytest
python3 -m pip install ruff==0.15.17 && python3 -m ruff check .
```

CI runs these, plus Home Assistant's hassfest and the HACS checks, on every
pull request and push to `main`.

### Releasing

Releases are made by hand: on GitHub, open **Actions → Release → Run
workflow** and run it on `main`. After CI passes, the workflow raises the
version in `manifest.json` by 0.01 (0.00 → 0.01, …, 0.99 → 1.00) and commits it
to `main`. It then tags that commit with the bare version (`0.01`, no `v`) and
publishes a GitHub release with generated notes and `breville_cooking.zip`,
which HACS offers as an update. To preview the next version, run
`python3 scripts/bump_version.py`.

`scripts/breville_probe.py` talks to the Breville cloud directly, without Home
Assistant, and logs every request and websocket message (redacted) to
`probe-output/`. It was used to verify the protocol on a Joule:

```sh
python3 scripts/breville_probe.py login
python3 scripts/breville_probe.py watch --seconds 600
python3 scripts/breville_probe.py start --temp 55 --minutes 30 --confirm-water
```

The protocol was recovered from the Breville+ Cooking Android app (1.96.0).
Breville can change its cloud at any time, which could break this integration.
