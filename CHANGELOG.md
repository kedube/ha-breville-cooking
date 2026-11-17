# Changelog

Notable changes in each release. Versions are the git tags and the `version`
in `custom_components/breville_cooking/manifest.json`. Add entries under
**Unreleased** with each change: the Release workflow makes that section the new
version's, and publishes it as the release notes' Highlights.

## Unreleased
### Joule
- **Start timer automatically works on the Joule.** The Joule ignored the
  setting and waited for **Continue** at temperature. Home Assistant now arms
  the timer the way the Breville+ app does, with a second request once the cook
  has started, and the timer starts as soon as the water is at temperature. If
  a Joule or Joule Turbo cook that Home Assistant started still waits for the
  food, Home Assistant presses **Continue** for it 3 seconds after it reaches
  temperature.
- **A running Joule cook can't be changed; stop it first.** The cloud accepted
  a new temperature or cook time, and Target temperature showed it, but the
  Joule went on heating to the old temperature. Changing Target temperature or
  Cook time during a Joule cook is now refused with "Stop the cook before
  changing this setting". The app doesn't offer it either.
- **A finished cook can't be changed.** Once the timer had run out, a new
  temperature or cook time was shown but not used. It's refused now: stop the
  cook to start another.

### Starting a cook
- **One cook at a time.** The Start cook action refuses to start a cook while
  one is running. Turning on **Cook** while it's already on no longer sends the
  next cook's settings, which replaced the running cook.
- **Temperatures and cook times outside the appliance's limits are refused,**
  with a message giving the limits in Home Assistant's temperature unit.
- **A temperature for an oven mode that cooks at a level, such as Broil, is
  refused** instead of being ignored.

### Connection
- **A connection that drops without closing is noticed.** Home Assistant pings
  Breville's cloud when nothing has arrived for 15 seconds, and reconnects once
  nothing, not even a reply, has arrived for 45 seconds. Requests give up after
  30 seconds instead of waiting indefinitely.
- **An old update no longer rolls the status back.** When Home Assistant
  connects, the cloud first sends the state it last stored, which can be about
  26 seconds old and still show the previous cook. Updates are now put in the
  appliance's own order, and an appliance that restarted is recognized.
- **A malformed update no longer breaks the appliance's entities.** A value
  that can't be read counts as missing, and a message that can't be handled is
  logged once.
- **An expired login is refreshed once, even when several requests find it
  expired together,** and a request refused after the refresh asks you to log
  in again.
- **An update from one appliance refreshes only that appliance's entities.**
- **Removing a device works while the integration isn't loaded.**

### Sidebar panel
- **A running Joule cook's settings are locked,** and so are a finished cook's,
  with the reason shown.
- **Pressing − or + quickly no longer selects the label's text** in Safari and
  the Home Assistant app on a Mac.

### Diagnostics
- **Diagnostics can be downloaded when setup fails,** and show the integration's
  state and whether the cloud answers pings.
- **Cloud errors name only the endpoint,** not the full address with your
  account ID or an appliance's serial number.

### Development
- **The probe script tries the Joule's auto-start:** `start --auto-start-timer`
  arms the timer as the app does, `auto-start-timer` arms a running cook's, and
  `watch` shows an armed timer and whether the cloud answers pings.
- **[docs/api.md](docs/api.md) records what was tried on a real Joule:** the
  auto-start request, edits that don't take, `defaultAutostart` being ignored,
  a new cook replacing an open one, and the cloud's stored state lagging.
- **Release notes come from this changelog,** with the commits since the last
  release.

## 0.13 — 2026-11-03
- **The Joule Turbo is now marked as tested, so Home Assistant can control it
  with no option turned on.** Before, Home Assistant could only show its status
  and stop a cook until you turned on Allow control of untested appliances. An
  owner has reported that it works, so you can now start and change its cooks
  from its entities and the sidebar panel with that option off.
- **Allow control of untested appliances now changes nothing for the supported
  appliances.** Every supported model has been tested. The option stays for
  models added later, before anyone has tried them.
- **Documentation now covers installing from the HACS default store.** The
  README no longer asks you to add the repository to HACS as a custom
  repository. The appliance report form now asks especially for reports from
  Sage accounts and the Joule Turbo.

## 0.12 — 2026-10-30
- **The sidebar panel uses your theme's panel background.** In Home Assistant
  2026.11 a theme can set a panel background, which can be a gradient or an
  image. The panel now shows it, and keeps its own background when the theme
  doesn't set one.
- **The integration no longer uses device registry features that Home Assistant
  is removing.** Updating each device's firmware version and matching the
  sidebar panel to its appliances used features that stop working in Home
  Assistant 2027.8 and 2027.10. Both now work in a way that also suits the
  oldest Home Assistant version the integration supports.
- **The integration now tells Home Assistant its category and how it connects.**
  It describes itself as a cooking appliance integration that connects through
  the cloud.

## 0.11 — 2026-10-27
- **Crispier air fry and Convection broil are no longer offered for the Joule
  Oven.** When sent from the cloud, either mode made the oven go back to idle
  once Start was pressed. They're gone from Mode and from the Start cook action,
  but Active mode still shows them if the oven reports them.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Level and Convection follow the running Joule Oven cook.** Before, they
  followed the settings for the next cook, so a cook started on the oven's own
  panel could show the wrong level or choices. Level now shows the running
  broil's or slow cook's level, and Convection offers the running mode's
  choices. While the oven keeps warm, Level stays the cook's.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Stopping a Joule Oven cook no longer shows Cooking for a moment.** When a
  cook started on the oven's own panel was stopped, the oven reported it once
  more with the heater off, and Status showed Cooking. Status now stays where it
  was until the oven goes idle.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Documentation now lists every Joule Oven mode as tested.** All 15 modes Home
  Assistant offers were started on a real oven. Cooks started on the oven itself
  show up and can be stopped.

## 0.10 — 2026-10-26
- **The end of a Joule Oven cook shows as Done even when Home Assistant's clock
  is a few seconds behind the oven's.** The oven's report that a cook is over
  could arrive while Home Assistant still counted a second or two on the timer,
  and Status then showed Ready for food. A timer within 5 seconds of its end now
  counts as run out.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Mode and Cook time keep showing the cook's settings when the Joule Oven's
  keep warm hour ends.** Before, the report that ended keep warm made Mode
  unknown and set Cook time to keep warm's 60 minutes. Now both stay the cook's
  while Status shows Done.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))

## 0.09 — 2026-10-25
### Joule Oven
- **Keep warm after a cook now shows as Keeping warm.** The oven keeps warm as a
  running cook in a separate mode, with a new hour-long timer, so Status showed
  Cooking and Cook time showed the hour. Now Status shows Keeping warm, Active
  mode shows keep_warm and Time remaining counts down the hour, while Mode and
  Cook time still show the cook's. If Home Assistant first sees the oven when
  it's already keeping warm, Mode and Cook time are unknown.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Target temperature no longer reads 0 °C (32 °F) during a broil or while the
  oven waits for Start.** A broil runs at a level and reports a setpoint of 0,
  and so does an oven waiting for Start. Target temperature now ignores that 0
  and falls back to the temperature set in Home Assistant.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Preheat no longer goes back during a Joule Oven preheat.** In an oven still
  warm from a broil, the sensor can cool before it heats, which made Preheat
  drop. Preheat now holds until the oven catches up.
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1))
- **Documentation now describes Keep warm on the Joule Oven.** The README also
  lists broil and Keep warm as tested on a real oven.

### Sidebar panel
- **The oven drawing keeps the cook's food in the oven while it keeps warm.**
  After a cook, the drawing shows the mode the food was cooked in, as Mode does.
  A keep warm started on the oven itself still draws its own covered dish.
- **The oven's display shows the target temperature while the oven waits for
  Start.** Before, the oven's 0 setpoint left the digits blank.

## 0.08 — 2026-10-25
### Sidebar panel
- **A new Breville+ sidebar panel shows each appliance as a drawing of the real
  thing, with its controls.** The overview has a card for each appliance,
  grouped by area, with its status, the oven's display, and the temperature and
  time left. With only one appliance, the panel opens straight to it. Each
  appliance's full view has Start, Stop and Continue, the settings for the next
  cook, a chart of the cook's temperature against its target, and the
  appliance's details. The sidebar entry is called Sage when every account is a
  Sage account.
- **The drawings follow what the appliance is doing.** The Joule sits in a clear
  container of water that circulates while it cooks, steams as it warms, and
  holds the bag once the food is in. The oven shows its display as the real one
  does, the rack and accessory for the mode, the food while it cooks, the
  elements glowing and the fan turning, in the oven's own brushed or black
  stainless finish.
- **Presets fill in the settings for a cook.** There are 15 built-in sous vide
  presets and 13 oven presets, based on USDA FSIS, the FDA Food Code and Douglas
  Baldwin's sous vide tables. Start then starts the cook, and a preset can't be
  applied while a cook runs. Administrators can save the current settings as a
  preset and rename, update or delete saved ones, which everyone shares; they're
  deleted when the last Breville+ Cooking account is removed.
- **The panel follows the same rules as the entities.** Anyone who can use Home
  Assistant can use it, untested appliances stay monitor-only unless you allow
  control, a running oven cook can't be changed, and Stop always works. While an
  account reloads, its appliances stay in the panel as unavailable.
- **The panel works with screen readers and the keyboard.** Every drawing is
  described in words, changes such as "ready for food" and "done" are announced,
  and everything can be reached from the keyboard.
- **New option: Show in the sidebar.** It's on at first and adds the panel for
  everyone who uses Home Assistant. Turning it off hides that account's
  appliances from the panel, and the panel leaves the sidebar once no account
  shows it.
- **The panel is translated into the same nine languages as the integration.**
  Printing in the drawings, such as the oven's display, stays as it is on the
  appliance.
- **Diagnostics include the sidebar panel's state.** They show whether the panel
  is turned on and in the sidebar, and the finish detected for each appliance.

### Joule Oven
- **The Joule Oven is now marked as tested, so it can be controlled without
  turning on Allow control of untested appliances.** Bake and air fry were tried
  on a real oven from the start to the end of the cook, including Continue after
  preheating ([#1](https://github.com/kedube/ha-breville-cooking/issues/1)).
  Other modes haven't been tried yet.
- **New Frozen food switch.** It cooks from frozen in the modes that offer it
  (Pizza, Cookies and Reheat), and is unavailable in other modes. Choosing a
  mode sets it to that mode's default. Before, the mode's default was always
  used.
- **Documentation.** The README explains when the oven ends preheating: when its
  sensor gets within 15 °C (27 °F) of the temperature it holds, or after 5
  minutes. From a cold start, Status can show Ready for food while Temperature
  still reads low.

### All appliances
- **New Preheat sensor showing how far preheating has got, in percent.** It's
  worked out from the temperature as the Breville+ app does, and is unknown when
  the appliance isn't preheating. On the Joule Oven it also counts the oven's
  5-minute preheat limit once Home Assistant has seen preheating start, so it
  nears 100% as preheating ends.
- **Configuration switches no longer turn off after a restart when they were
  last unavailable.** Start timer automatically and Keep warm read an
  unavailable state as off. They now skip it and keep their default setting.

## 0.07 — 2026-10-25
- **Continue on a Joule Oven now moves a waiting cook on to its cook step, as
  the Breville+ app does.** The oven ignored the food-in command that Continue
  sent before, so its timer didn't start after preheating
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1)). This hadn't
  been tried on a real oven yet in this release.
- **A running Joule Oven cook's temperature and time can no longer be changed.**
  The oven accepted a change but kept its settings, and the Breville+ app offers
  no way to change them either. Changing Target temperature or Cook time during
  an oven cook now shows "Stop the cook before changing this setting."
- **During an oven cook, Cook time shows the cook's length.** It showed the time
  left before. Time remaining still shows it.
- **Documentation.** The README explains that if the oven's timer doesn't start
  by itself, you press Continue once Status shows Ready for food, and that
  pressing Start on the oven at that point cancels the cook.

## 0.06 — 2026-10-25
- **Time remaining, Cook end and Cook time now follow a Joule Oven's timer.**
  The integration didn't recognize the timer a real oven reports, so Time
  remaining and Cook end stayed empty and Cook time showed 0 during a cook
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1)).
- **Status changes to Done when a Joule Oven's timer runs out.** The oven turns
  itself off at that point, and Status could show Ready for food instead.
  Cooking now turns off and Continue becomes unavailable, while Cook stays on
  until you turn it off to close the cook on the oven.
- **After an oven cook ends, the settings entities go back to the next cook.**
  Target temperature, Cook time, Mode and Convection kept showing the finished
  cook until Cook was turned off. They now show the settings for the next cook,
  and changes apply to it.
- **Temperature is unknown while the Joule Oven is idle.** An idle oven stops
  updating its reading, so Temperature could show 59 °C hours after the oven
  cooled.
- **Cook time is unknown while the Joule Oven preheats.** It showed 0, because
  the oven reports its timer only once preheating is done.
- **Start timer automatically is on at first for the Joule Oven, as in the
  Breville+ app.** The oven then starts its timer by itself once preheating is
  done.
- **Continue on a Joule Turbo or Joule Oven now tells the appliance where the
  cook is, as the Breville+ app does.** Before, it sent the same short command
  as the Joule. A real Joule Oven answered that command without starting its
  timer.
- **Documentation.** The README explains that the oven's Temperature reads below
  its target while it cooks, what happens when the timer runs out, and that
  changing a running oven cook doesn't work yet. The Joule Oven's support status
  now lists bake and air fry, with their timers, as tried on a real oven.

## 0.05 — 2026-10-24
- **Target temperature is now right on a Joule Oven set to °F.** The oven rounds
  its °C setpoint to its own steps, so a 200 °F cook showed as 95 °C (203 °F).
  The integration now uses the oven's °F setpoint when the oven is set to °F
  ([#1](https://github.com/kedube/ha-breville-cooking/issues/1)).
- **Convection shows the fan setting of a running Joule Oven cook.** A real oven
  reports the fan as a plain number, which the integration didn't read, so
  Convection was unknown during a cook.
- **Diagnostics redact the name and serial number a Joule Oven reports in its
  own state.** The oven's name contains its serial number, and both could appear
  in downloaded diagnostics.
- **Documentation.** The Joule Oven's support status now says starting and
  stopping a bake was tried on a real oven. The README now says that after a
  remote start, the oven waits for Start to be pressed on its panel, as it does
  for cooks started from the Breville+ app.

## 0.04 — 2026-10-24
- **The Joule Turbo and Joule Oven get whole numbers in the same form the
  Breville+ app sends them.** Before, a whole temperature such as 60 °C was sent
  as 60.0. Now it is sent as 60 when a cook starts, when the temperature of a
  running cook changes, and for the oven's "A bit more" step.
- **Diagnostics remove more personal data.** Before, serial numbers kept their
  last four digits, and your email and appliance names were masked only when
  they made up a whole value. Now your email, name and account IDs, login
  tokens, appliance names, serial numbers and network addresses are removed
  wherever they appear, even inside other text, along with anything that looks
  like an email or MAC address.
- **Documentation adds a screenshot and a description of the cloud API.** The
  README shows a Joule's device page during a cook, and `docs/api.md` describes
  the Breville cloud API and marks which parts were verified on a real Joule.

## 0.03 — 2026-10-24
- **The add button on the integration's page now says "Add account" instead of
  "Add hub".** It is translated into all nine supported languages.

## 0.02 — 2026-10-24
- **Documentation now points to the ChefSteps Joule Sous Vide integration for
  Bluetooth control.** The README and the new-issue page link to it for
  controlling a Joule (CSJ100) over Bluetooth, which this integration can't do.
  The Sage Coffee link for espresso machines is reworded.

## 0.01 — 2026-10-24
### First release
- **Controls Breville+ Cooking appliances through the Breville cloud, the same
  cloud the Breville+ Cooking app uses.** The Joule (CSJ100) is tested on a real
  appliance. The Joule Turbo (BSV600) and Joule Oven Air Fryer Pro (BOV950) are
  built from the app's code and untested. Other appliances on the account are
  ignored.
- **Setup uses the app's email and password and a choice of Breville or Sage.**
  Each supported appliance becomes a device, named as in the app. Home Assistant
  keeps a login session, not the password, and asks you to log in again when it
  expires. It needs Home Assistant 2026.2 or newer, and accounts with
  multi-factor authentication aren't supported.
- **Each appliance has Status, Temperature, Time remaining, Cook end and Error
  sensors, and Cooking and Problem binary sensors.** Status shows Idle,
  Preheating, Ready for food, Cooking, Done, Keeping warm, Press the button on
  the appliance, Error, Updating or Offline.
- **Cooks are run with the Target temperature and Cook time numbers, the Cook
  switch, the Continue button and the Start timer automatically switch.**
  Settings for the next cook are kept in Home Assistant and sent when a cook
  starts. While a cook runs, changing Target temperature or Cook time changes
  it. For sous vide, a cook time of 0 holds the temperature until you stop it.
- **The Joule Oven also has Mode, Convection and Level selects, a Keep warm
  switch, a Door binary sensor and an Active mode sensor.** Mode offers Bake,
  Air fry, Roast, Broil, Pizza and 12 other modes. Toast, Bagel and Crispy
  reheat can't be started from Home Assistant, but Active mode shows them.
- **The Start cook action (`breville_cooking.start_cook`) starts a cook with its
  own temperature, duration and oven settings.** Fields you leave out come from
  the appliance's entities, or from the mode's defaults when you set a mode.
- **Untested appliances are monitor-only until you turn on Allow control of
  untested appliances in the integration's options.** Until then, Home Assistant
  shows the Joule Turbo's and Joule Oven's status and can stop a cook, but can't
  start or change one.
- **Breville's cloud pushes updates as they happen, usually within a second or
  two.** If the connection drops, it reconnects by itself. The account's
  appliance list is checked every 30 minutes: new appliances appear by
  themselves, and you can delete removed ones from their device page.
- **Diagnostics include each appliance's raw state and recent cloud messages.**
  Your email, login tokens, appliance names and network addresses are removed,
  and serial numbers are cut to their last four digits.
- **Screens, entity names and messages are available in English, German, French,
  Dutch, Spanish, Simplified Chinese, Italian, Polish and Swedish.**
