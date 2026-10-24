# Breville+ Cooking for Home Assistant

[![CI](https://github.com/kedube/ha-breville-cooking/actions/workflows/ci.yml/badge.svg)](https://github.com/kedube/ha-breville-cooking/actions/workflows/ci.yml)

Control your Breville+ Cooking appliances from Home Assistant: start and stop
cooks, change the temperature and timer, and get notified when the water is
ready or the food is done. It uses the same Breville cloud as the Breville+
Cooking app.

This integration is unofficial, and isn't affiliated with or endorsed by
Breville.

## Supported appliances

| Appliance | Model | Status |
|---|---|---|
| ChefSteps Joule Sous Vide | CSJ100 | Tested on a real appliance |
| Joule Turbo Sous Vide | BSV600 | Built from the app's code; untested |
| Joule Oven Air Fryer Pro | BOV950 | Built from the app's code; untested |

Other appliances on the account, such as espresso machines and other ovens,
are ignored. If you have a BSV600 or BOV950, please try it and
[open an issue](https://github.com/kedube/ha-breville-cooking/issues) with
your [diagnostics](#troubleshooting), whether it works or not.

## Requirements

- Home Assistant 2026.2 or newer.
- The Breville+ account you use in the Breville+ Cooking app. Accounts with
  multi-factor authentication aren't supported yet.
- The appliance set up in the app and connected to Wi-Fi. A Joule set to
  "Bluetooth only" can't be reached.

## Installation

### HACS

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kedube&repository=ha-breville-cooking&category=integration)

Or, in HACS, add `https://github.com/kedube/ha-breville-cooking` as a custom
repository of type *Integration*. Then download **Breville+ Cooking** and
restart Home Assistant. HACS offers each new release as an update.

### Manually

Download `breville_cooking.zip` from the
[latest release](https://github.com/kedube/ha-breville-cooking/releases/latest),
unzip it into `config/custom_components/breville_cooking`, and restart Home
Assistant.

## Setup

[![Start setting up Breville+ Cooking](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=breville_cooking)

Or go to **Settings → Devices & services → Add integration** and choose
**Breville+ Cooking**. Log in with your Breville+ email and password. Each
supported appliance on the account becomes a device, named as in the app.

Your password is only sent to Breville. Home Assistant keeps a login session,
not the password, and asks you to log in again if the session expires. To add
another Breville+ account, add the integration again.

## Entities

Every appliance has:

| Entity | Type | What it does |
|---|---|---|
| Status | Sensor | What the appliance is doing: Idle, Preheating, Ready for food, Cooking, Done, Keeping warm, Press the button on the appliance, Error, Updating or Offline. |
| Temperature | Sensor | The water or oven temperature. |
| Time remaining | Sensor | Time left on the timer. |
| Cook end | Sensor | When the timer will finish. |
| Cooking | Binary sensor | On from the start of a cook to its end, including preheating and waiting for the food. |
| Problem | Binary sensor | On while the appliance reports an error. |
| Error | Sensor (diagnostic) | The error, such as Low water level or Tipped over. |
| Target temperature | Number | The temperature for the next cook, or of the running one. |
| Cook time | Number | The timer in minutes, for the next cook or the running one. For sous vide, 0 holds the temperature until you stop it. |
| Cook | Switch | Turn on to start a cook with these settings, and off to stop it. |
| Continue | Button | Tells the appliance the food is in, which starts the timer, or that it's out. Available only while the appliance is waiting for this. |
| Start timer automatically | Switch (configuration) | Starts the timer as soon as the temperature is reached, instead of waiting for **Continue**. |

The oven also has:

| Entity | Type | What it does |
|---|---|---|
| Mode | Select | Bake, Air fry, Roast, Broil, Pizza and 12 other modes. Choosing one resets the other settings to that mode's defaults. |
| Convection | Select | The fan: Off, On or Super, as the mode allows. |
| Level | Select | Broil intensity (Low, Medium or High) or slow-cook level (Low or High). These modes use it instead of Target temperature. |
| Keep warm | Switch (configuration) | Keeps the food warm when the cook finishes. |
| Door | Binary sensor | Whether the door is open. |
| Active mode | Sensor | The mode of the running cook, including cooks started on the oven. |

Settings for the next cook are kept in Home Assistant, survive restarts, and
go to the appliance only when a cook starts. Changing settings in the
Breville+ app doesn't change them here.
While a cook runs, **Target temperature** and **Cook time** show the running
cook, and changing them changes it. The oven's **Mode**, **Convection** and
**Level** can only be changed while it's idle. Like the app, the integration
keeps to each model's temperature and time limits.

### A sous vide cook, step by step

1. Set **Target temperature** and **Cook time**, then turn on **Cook**.
   Status changes to Preheating.
2. At temperature, Status changes to Ready for food. Put the food in and press
   **Continue** to start the timer. With **Start timer automatically** on, the
   timer starts without waiting for **Continue**.
3. While the food cooks, **Time remaining** counts down and **Cook end** shows
   when it will finish.
4. When the timer ends, Status changes to Done. Take the food out and press
   **Continue**, or turn off **Cook**.

The oven may ask you to press Start on its panel before it begins. Status then
shows Press the button on the appliance.

## Actions

### Start cook (`breville_cooking.start_cook`)

Starts a cook with the settings you give, without changing the appliance's
entities. Target the appliance's **Cook** switch.

| Field | Description |
|---|---|
| `temperature` | Target temperature, in your Home Assistant unit. |
| `duration` | Cook time, such as `"01:30:00"`. For sous vide, leave it out to hold the temperature until you stop it. |
| `mode` | Oven only: the mode, such as `bake`, `air_fry`, `roast` or `broil`. |
| `convection` | Oven only: `off`, `on` or `super`. |
| `level` | Oven only: `low`, `medium` or `high` for broil modes, and `low` or `high` for slow cook. |
| `auto_start_timer` | Start the timer once the temperature is reached. |
| `keep_warm` | Oven only: keep the food warm when the cook finishes. |

Fields you leave out come from the appliance's entities. If you set `mode`,
they come from that mode's defaults instead, apart from `auto_start_timer` and
`keep_warm`.

```yaml
action: breville_cooking.start_cook
target:
  entity_id: switch.joule_cook
data:
  temperature: 57
  duration: "01:30:00"
```

The standard actions work too. For example, `switch.turn_on` on **Cook**
starts a cook with the entities' settings, `switch.turn_off` stops it, and
`button.press` presses **Continue**.

## Examples

These examples assume an appliance named Joule. Your entity IDs follow the
appliance's name in the Breville+ app.

Get a notification when the water is ready for the food:

```yaml
alias: Joule ready for food
triggers:
  - trigger: state
    entity_id: sensor.joule_status
    to: ready
actions:
  - action: notify.notify
    data:
      message: The water is at temperature. Add the food and press Continue.
```

Get a notification 10 minutes before the cook ends:

```yaml
alias: Joule almost done
triggers:
  - trigger: time
    at:
      entity_id: sensor.joule_cook_end
      offset: "-00:10:00"
actions:
  - action: notify.notify
    data:
      message: Ten minutes to go.
```

Heat the water before you get home, and hold it at temperature:

```yaml
alias: Preheat the Joule
triggers:
  - trigger: time
    at: "17:30:00"
actions:
  - action: breville_cooking.start_cook
    target:
      entity_id: switch.joule_cook
    data:
      temperature: 57
```

## Safety

Cooks start remotely, with nobody nearby. Only start a sous vide when it's in
water, and an oven only when there's nothing inside that shouldn't be heated.
For a delayed start, don't leave raw food sitting in unheated water.
UL-certified Joules (North America) wait for a press of their top button
before cooks above 85 °C.

## Data updates

Home Assistant keeps one connection open to Breville's cloud, which pushes
changes as they happen, usually within a second or two. If the connection
drops, it reconnects by itself: first after 5 seconds, then less often, up to
5 minutes apart. Entities are unavailable while it's disconnected. It also
checks the account's list of appliances every 30 minutes.

## Known limitations

- The BSV600 and BOV950 haven't been tried on real appliances.
- Accounts with multi-factor authentication can't log in.
- The BSV600's Turbo mode isn't offered.
- The oven's Toast, Bagel and Crispy reheat modes can't be started from Home
  Assistant, though **Active mode** shows them.
- An appliance added to the account after setup only appears after you reload
  the integration.
- There's no local control. Breville can change its cloud at any time, which
  could break this integration.

## Troubleshooting

- **Entities are unavailable:** Home Assistant can't reach Breville's cloud,
  and keeps trying. If Status shows Offline instead, the appliance itself is
  off or disconnected; check it in the Breville+ app.
- **Asked to log in again:** the Breville session expired. Follow the prompt
  in **Settings → Devices & services** and enter your password.
- **A new appliance is missing:** go to **Settings → Devices & services →
  Breville+ Cooking**, then ⋮ → **Reload**.
- **Anything else:** on the same page, choose **Enable debug logging**,
  reproduce the problem, then choose **Disable debug logging** to download the
  log.

When you report a problem or want support for a new model or firmware, attach
the integration's diagnostics: go to **Settings → Devices & services →
Breville+ Cooking**, then ⋮ → **Download diagnostics**. The file contains the
appliances' raw state, without your email, login tokens or the appliances'
network addresses, and with serial numbers cut to their last four digits.
Look it over before posting it publicly.

## Removing the integration

1. Go to **Settings → Devices & services → Breville+ Cooking**, then ⋮ →
   **Delete**.
2. Remove the files. In HACS, open **Breville+ Cooking** and choose ⋮ →
   **Remove**. If you installed manually, delete
   `config/custom_components/breville_cooking`. Then restart Home Assistant.

This doesn't change anything on your Breville+ account or appliances.

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

### Probe script

`scripts/breville_probe.py` talks to the Breville cloud directly, without Home
Assistant, and logs every request and websocket message (redacted) to
`probe-output/`. It was used to verify the protocol on a Joule:

```sh
python3 scripts/breville_probe.py login
python3 scripts/breville_probe.py watch --seconds 600
python3 scripts/breville_probe.py start --temp 55 --minutes 30 --confirm-water
```

The protocol was recovered from the Breville+ Cooking Android app (1.96.0).

## Trademarks

Breville, Breville+ and their logos are trademarks of Breville. The icon and
logo in `custom_components/breville_cooking/brand/` are from the Breville+
Cooking app, and are used only to identify the appliances this integration
works with. Home Assistant shows them from version 2026.3.
