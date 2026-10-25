# Breville+ sidebar panel: implementation plan

Plan, 2026-10-25, updated as phases 0–3 were built on the `sidebar-panel`
branch. Modeled on the Sub-Zero panel (`ha-subzero/docs/sidebar-panel-plan.md`),
and reusing its code where it fits.

## 1. Decisions

From the 2026-10-25 questions:

- **Panel only.** It's a sidebar panel. There are no Lovelace cards and no
  dashboard resource.
- **Sidebar entry:** "Sage" when every account set up is a Sage account, and
  "Breville+" otherwise, including a mix of both. The icon is
  `mdi:pot-steam-outline`, and the entry is visible to every user. The name is
  a brand, so it isn't translated.
- **On by default.** A Configure option turns it off.
- **Layout:** as in Sub-Zero, an overview with one card per appliance, grouped
  by area. Tapping a card opens a full view with every control. With only one
  appliance, the panel opens straight to its full view.
- **Coverage:** every supported appliance, which means the Joule (CSJ100), the
  Joule Turbo (BSV600) and the Joule Oven Air Fryer Pro (BOV950). That
  includes every oven mode, even the ones that can only be started on the oven
  itself.
- **Everyone can view and control.** The integration's rules still apply:
  - untested models are monitor-only unless the option allows control;
  - a running oven cook can't be changed;
  - Stop always works.
- **Realistic drawings:** each drawing is modeled on product photos and reads
  like a product rendering, not a cartoon. Photos are references only, and are
  never traced, embedded or committed.
- **No branding in drawings:** no Breville, Sage, Joule or ChefSteps logos.
- **Finishes are detected.** There's no Appearance setting:
  - the Joule and the Joule Turbo have a white body with polished stainless
    trim, since the two look the same;
  - the oven's finish comes from its item number, else from the colour code in
    its serial number, else it's brushed stainless (§3.3).
- **Sous vide scene:** the circulator is clipped in a clear container of
  water. The water ripples while it circulates and steams as it heats, and a
  food bag appears once the food is in.
- **Oven scene, in full:**
  - the rack sits at the mode's position, holding that mode's accessory;
  - food appears while it cooks;
  - the elements glow the way the mode uses them;
  - the fan turns with convection;
  - the door opens when it's open.
- **Temperature chart:** the current cook's temperature against its target.
- **Presets:**
  - built-in sous vide and oven presets;
  - custom presets, kept in Home Assistant and shared by everyone, which only
    admins can add, change or delete;
  - a preset fills in the cook settings, and Start starts the cook.
- **Screen readers:** the whole panel works with one. Each drawing has a text
  description of its state, and every control is labeled and works from the
  keyboard.
- **Release:** 0.08, a regular release after 0.07. You'll ask CityDweller to
  try it with VoiceOver afterwards.

## 2. How it fits together

```
 Breville cloud ──push──▶ coordinator ──▶ entities (sensor, number, select, switch, button)
                              │                  ▲              │
                              │ structure,       │ service      │ live state
                              │ locks, extras    │ calls        │ (hass.states)
                              ▼                  │              ▼
                 panel_api.py (websocket) ───────────────▶ <breville-cooking-panel> (Lit)
                 panel_spec.py (model → drawing spec)        overview / full view
                 presets.py + presets store (.storage)       drawings, controls, chart
```

- The panel reads live values from `hass.states`. It controls appliances only
  through the existing entities:
  - Cook is `switch.turn_on` and `switch.turn_off`;
  - Continue is `button.press`;
  - settings use `number.set_value`, `select.select_option` and the option
    switches.
- The one exception is applying a preset, which sets every cook setting at
  once (§3.4).
- A websocket subscription sends what the frontend can't work out:
  - which entity holds which key;
  - the drawing spec (kind and finish);
  - the oven's mode table;
  - lock reasons;
  - the oven's sensor target;
  - the presets.

## 3. Backend (Python)

### 3.1 Option

- `const.py`: add `CONF_SHOW_SIDEBAR_PANEL = "show_sidebar_panel"` and
  `DEFAULT_SHOW_SIDEBAR_PANEL = True`, the names Sub-Zero uses.
- `config_flow.py`: add a boolean to the options step, "Show in the sidebar".
  It's saved only when it's `False`. A missing key means on, so existing users
  get the panel when they upgrade, with no migration.
- **No reload:** options already apply without one, since the untested-control
  option is read live. The panel follows Home Assistant's config entry change
  signal instead, which also covers an entry that's waiting to retry its
  setup.
- Add the label and description to `strings.json` and the 8 translations.
  `test_translations.py` already checks they match.

### 3.2 `frontend.py`

Copied from Sub-Zero's, minus its Sub-Zero specifics:

- **Static files:** serve `custom_components/breville_cooking/frontend/` at
  `/breville_cooking` with cache headers.
  - The module URL carries `?v=<manifest version>-<first 8 hex digits of the
    bundle's SHA-256>`.
  - So every build gets a new URL, not just every release.
- **Panel registration:**
  `panel_custom.async_register_panel(frontend_url_path="breville-cooking",
  webcomponent_name="breville-cooking-panel", sidebar_title=…,
  sidebar_icon="mdi:pot-steam-outline", module_url=…, require_admin=False)`.
  The panel path must differ from the static path, which Sub-Zero and
  ha-norman both learned.
- **One panel for the integration,** listing the appliances of every entry that
  has the option on.
  - An entry that's reloading or retrying setup keeps its appliances in the
    panel, marked unavailable.
  - Disabling an entry, turning its option off or removing it takes its
    appliances away at once, and the panel too if no entry is left.
- **Title:** "Sage" when every listed entry's brand is Sage, and "Breville+"
  otherwise. When that changes, the panel is registered again with the new
  title.
- **Best effort:** a failure is logged and never fails setup.
- `manifest.json`: add `after_dependencies: ["frontend", "http",
  "panel_custom"]`.

### 3.3 `panel_spec.py` (model → drawing spec)

This is a pure module with no Home Assistant imports, tested table-first.

- **`detect_finish(model, item_number, serial)`:**
  - CSJ100 and BSV600: `white_polished`, a white body with polished stainless
    trim;
  - BOV950, from the item number: `BSS` is `brushed_stainless` and `BST` is
    `black_stainless`;
  - otherwise, from the serial's colour code (the app's `parseSerialNumber`):
    the 5th character of `^(SS)(B)(R)(C)(PP)(V)(\d{9})$`, where A is stainless
    steel and H is black stainless steel;
  - otherwise `brushed_stainless`.
  - The serial is read only here. It's never sent to the browser or logged.
- **`oven_mode_table()`** is built from `OVEN_MODES` in `appliance.py`, so
  there's one source. Each mode gets:
  - its type: temperature, broil level or slow-cook level;
  - its limits and defaults;
  - its rack position;
  - whether it preheats;
  - its convection choices;
  - whether it offers Frozen and Keep warm;
  - drawing hints for the accessory, the food and the elements (§5.3).
  - Modes that can only be started on the oven get drawing hints too: toast,
    bagel, crispy reheat and keep warm.

### 3.4 `panel_api.py` (websocket)

**`breville_cooking/panel/subscribe`** (all users) sends a snapshot, then
per-appliance updates. One appliance looks like this:

```json
{
  "device_id": "<HA device id>",
  "entry_id": "…",
  "model": "BOV950",
  "kind": "oven",
  "finish": "brushed_stainless",
  "entities": {"cook": {"switch": "switch.kitchen_oven_cook"},
               "target_temperature": {"number": "number.kitchen_oven_target_temperature"},
               "…": {}},
  "control_allowed": true,
  "can_edit_cook": false,
  "sensor_target_c": 161,
  "available": true
}
```

- **Shared data:** each message also carries `oven_modes` and `presets`
  (built-in and custom), when they change.
- **The entity map** comes from the entity registry. The unique ID is
  `{serial}_{key}`; strip the appliance's serial to get the key. Disabled
  entities are left out, and the serial never leaves the backend.
- **`sensor_target_c`** is the oven's `heater.temp_sp_m` while it cooks: the
  temperature it holds its own sensor at (§5.3).
- **Updates are sent when** any of these happens, and only when something
  changed:
  - entities are added, removed or renamed;
  - the untested-control option changes;
  - `sensor_target_c` changes;
  - an entry is set up or unloaded;
  - a preset is saved or deleted.
- **Names and areas** come from `hass.devices` and `hass.areas` in the
  frontend.

**`breville_cooking/panel/apply_preset`** (all users) takes
`{device_id, preset_id}`.

- It checks the preset against the appliance's kind and limits.
- It then sets every cook setting at once: the mode's defaults first, as the
  Mode select does, then the preset's values.
- It's refused while a cook is running: "Stop the cook first."
- **Why not entity calls:** an oven preset would need up to seven calls in a
  fixed order, since a Mode change resets the other settings. Frozen also has
  no entity yet (§3.6).

**`breville_cooking/panel/save_preset`** and
**`breville_cooking/panel/delete_preset`** are `@require_admin`.

- `save_preset {device_id, name}` saves that appliance's current settings as a
  new preset. With `preset_id`, `name` renames it and `device_id` replaces its
  settings with the appliance's current ones.
- Errors carry a code the panel translates: `cook_running`,
  `unknown_appliance`, `unknown_preset`, `invalid_preset`, `too_many_presets`,
  `unavailable`.

### 3.5 Presets

- **Built-in:** `presets.py` holds the built-in table (§5.4). Each entry has an
  ID, a kind (`sous_vide` or `oven`) and its settings. Names live in the
  frontend's languages, keyed by ID.
- **Oven temperatures:** an oven preset carries a Celsius and a Fahrenheit
  temperature, each a round number. The one matching Home Assistant's unit
  system is used, so 350 °F stays 350 °F.
  - The oven rounds to its own steps. 175 °C would come back as 345 °F, so
    using the matching unit avoids that.
- **Custom:** stored in `Store(hass, 1, "breville_cooking.presets")` as
  `{id, kind, name, settings}`.
  - Up to 50 of them, with names up to 40 characters.
  - They're removed with the last entry (`async_remove_entry`).
- **Fit:** a preset appears only for appliances whose limits it fits. That
  means 20–98 °C for the CSJ100, 20–92 °C for the BSV600, and the mode's
  limits for the oven.
- **Tests:** every built-in preset passes the same checks as a custom one, and
  the sous vide safety rule (§5.4).
- **Custom presets** only have to fit the appliances' limits. The safety rule is
  for the built-in ones; custom ones are up to the admins who save them.

### 3.6 New entities

- **Frozen food** switch, for the oven: a configuration switch like Keep warm.
  - It's available only for modes that offer it: pizza, cookies and reheat.
  - A Mode change resets it to the mode's default.
  - The setting already exists (`CookSettings.frozen`), but has no entity.
- **Preheat** sensor (%), for every appliance, using the app's formula
  (`getPreheatProgress`):
  - **Oven:** `cur_temp / (temp_sp_m − 15)`, or
    `cur_temp / (0.9 × temp_sp_m)` at 150 °C and below, capped at 100. The
    oven also ends preheating after 5 minutes (issue #1), so once Home
    Assistant has seen preheating start, it's the further along of that and
    the time out of 5 minutes.
  - **Joule and Joule Turbo:** `current / target`, capped at 100.
  - It has a value while preheating, and is unknown otherwise.
- **Translations and icons:** the names go in `strings.json` and the 8
  translations, and the icons in `icons.json`.

### 3.7 Diagnostics, docs

- **Integration diagnostics:** add
  `panel: {enabled_entries, registered, title, module_url}`, each appliance's
  finish, and the number of custom presets. Preset names are left out.
- **README:**
  - a new "Sidebar panel" section with light and dark screenshots, covering
    presets and screen readers, with a note that presets are a starting point
    and a trusted cooking guide comes first;
  - an Options table row for the new option.

### 3.8 Backend tests

- **`test_panel.py`,** modeled on Sub-Zero's:
  - the panel is registered by default, and not when the option is off;
  - it's removed on unload;
  - two entries share one panel;
  - the title reads "Sage", "Breville+", or "Breville+" for a mix;
  - toggling the option updates the sidebar without a reload;
  - the static path is registered once, and the module URL carries the version;
  - registration failures don't break setup.
- **`test_panel_api.py`:**
  - snapshots for a Joule, a Joule Turbo and the oven (§7);
  - disabled entities are left out;
  - updates arrive on entity changes, option changes and preset saves;
  - non-admins can't save or delete presets;
  - invalid presets are refused, and so is applying one during a cook.
- **`test_panel_spec.py`:**
  - finishes come out right from item numbers and serial colour codes;
  - the mode table matches `OVEN_MODES`.
- **The new entities:** Frozen food and Preheat.

## 4. Frontend

### 4.1 Toolchain

- **Same stack as Sub-Zero:** Lit 3, TypeScript (strict), esbuild, vitest with
  happy-dom, and playwright-core for the gallery. Add axe-core for
  accessibility checks in the gallery run.
- **Source** lives in a top-level `frontend/`. `npm run check` runs typecheck,
  tests and build.
- **The build** is one minified ES module,
  `custom_components/breville_cooking/frontend/breville-cooking-panel.js`,
  committed. The release zip is built from `custom_components/breville_cooking`,
  so it picks the bundle up without changes.
- **CI:** add a `frontend` job to `ci.yml`. It runs `setup-node` (24), `npm ci`
  and `npm run check`, then `git diff --exit-code` on the bundle, so a stale
  bundle fails.
- **Self-contained:** drawings are SVG generated in code, with no image files.
  The panel uses only the `hass` object, and none of Home Assistant's internal
  `ha-*` elements.
- **Copied from Sub-Zero and adapted** (it's your own code):
  - the panel shell;
  - the card frame;
  - the controls: setpoint stepper, duration, select, toggle, action with
    confirmation, countdown and reading;
  - the data helpers: subscription, history, locale and route;
  - the i18n loader;
  - the gallery and render scripts.
- **New here:** the sous vide and oven drawings, presets, the chart, and the
  accessibility layer.

Layout:

```
frontend/src/
  breville-cooking-panel.ts  panel element, routing, toolbar
  data/                      subscription, joins with hass.devices/areas/states, history, presets
  kinds/                     view models: common.ts, sous-vide.ts, oven.ts
  views/                     overview.ts, appliance-view.ts, presets.ts, chart.ts
  card/                      header, status pill, display, info panel, confirm bar
  controls/                  stepper, duration, segmented, mode picker, toggle, action, countdown
  drawings/                  materials.ts;
                             sous-vide/ (circulator, container, water, bag);
                             oven/ (body, door, panel, cavity, racks, accessories, food, elements, fan)
  a11y/                      drawing descriptions, announcer
  i18n/                      en, de, es, fr, it, nl, pl, sv, zh-Hans
frontend/gallery/            dev page: every model × finish × state × mode, light and dark
frontend/test/               unit tests
```

### 4.2 Panel shell

- **Routes:** `/breville-cooking` is the overview, and
  `/breville-cooking/<device_id>` is an appliance's full view. Both can be
  linked to directly, and Back works.
- **One appliance:** `/breville-cooking` shows its full view, with no Back
  button. A second appliance brings the overview back.
- **Toolbar:** the sidebar title ("Breville+" or "Sage"), a menu button on
  narrow screens, and a back button in the full view.
- **Grouping:**
  - by device area, in Home Assistant's area order, with "No area" last;
  - within an area, ovens first, then sous vide, then by name.
- **Empty state:** with no appliances, the panel links to Configure.
- **Theme:** Home Assistant's CSS variables, so light and dark both work. The
  drawings keep their own materials.
- **Languages:** panel text is bundled for the 9 languages and picked from
  `hass.language`.
  - Entity states use `hass.formatEntityState`.
  - Numbers, times and temperatures follow `hass.locale` and the unit system.

### 4.3 Overview card

- **Header:** the appliance name, and a status pill whose colour follows the
  state:
  - neutral: Idle;
  - warm: Preheating NN%, Cooking, Keeping warm;
  - green: Ready for food, Done;
  - amber: Door open, Press Start on the oven;
  - red: Error;
  - gray: Offline, Updating.
- **The live drawing.**
- **Display:** amber digits as on Sub-Zero's cards, only where the real
  appliance has a display. The oven's shows its temperature or the time left.
  The Joules have no display, so their readout sits on the container instead:
  the water temperature, plus the target while heating.
- **Info panel:** 2–3 rows (§6).
- **Offline appliances** are greyed out.

### 4.4 Full view

- **At the top:** the large drawing, the display, the status pill, and a
  preheat ring while preheating.
- **Sections:**
  1. **Cook:** the temperature now and the target, time left and the end time,
     and for the oven the door. Its actions:
     - **Start** (`switch.turn_on` on Cook), with a confirm bar: "Start the
       oven at Air fry 400 °F for 18 minutes?";
     - **Stop** (`switch.turn_off`), which reads "Finish" once an oven cook is
       over and the oven has turned itself off;
     - **Continue** (`button.press`), labeled for what it does: "Food is in:
       start the timer" or "Food is out".
  2. **Settings,** for the next cook or the running one:
     - **Sous vide:** a target stepper, the cook time with Hold, and Start
       timer automatically. While cooking, changes edit the cook, as on the
       device page.
     - **Oven:** a mode picker (a tile per mode), temperature or level, time,
       convection, Frozen food, Keep warm, and Start timer automatically.
       While cooking it shows the running cook read-only: "A running oven cook
       can't be changed."
  3. **Presets** (§4.6).
  4. **Temperature chart** (§4.7).
  5. **Details:** model, finish, firmware, and any error with its explanation.
- **Locks:** a disabled control shows its reason. For untested models, admins
  get a link to Configure.
- **Unavailable entities** show "—".
- **Errors:** a rejected call shows Home Assistant's message inline.

### 4.5 Drawing system

- **Parametric Lit `svg` templates** for the two kinds, built from shared
  parts (§5).
- **Proportions** come from published dimensions:
  - the oven is 21.4 × 17.3 × 12.7 in;
  - the Joule is drawn to its height, in a container sized to match.
- **Fitting:** every overview card fits its drawing to the same height.
- **Materials** (`materials.ts`):
  - brushed stainless and black stainless;
  - the Joule's white polycarbonate and polished stainless;
  - door glass, water, steam and quartz glow.
- **Gallery:** `npm run gallery` renders every model in every finish and state,
  and every oven mode, light and dark. It's used for review, for screenshot
  tests and for the axe-core run.

### 4.6 Presets view

- **Lists:** built-in presets first, then custom ones. Each row shows the name
  and the settings: "56 °C · 1 h 30 min", or "Air fry · 400 °F · 20 min".
- **Using one:** tapping a preset fills in the settings (`apply_preset`) and
  moves focus to Start. Nothing starts on its own.
- **Hidden** when a preset doesn't fit the appliance's limits, and **disabled**
  during a cook.
- **Admins:** "Save current settings as a preset", plus rename, change and
  delete, with a confirmation before deleting.

### 4.7 Temperature chart

- **What it plots:** the current temperature against the target, since the
  cook started (the last time Cook turned on).
  - It's read from `history/history_during_period`, then extended live from
    `hass.states`.
  - The target is drawn as a step line.
- **The oven:** a dashed line at `sensor_target_c`, captioned to say that the
  oven holds its own sensor there, below the setpoint. Otherwise the gap looks
  like a fault.
- **After a cook:** it keeps showing that cook until the next one starts.
- **Drawing:** hand-drawn SVG, with no chart library, in the Home Assistant
  unit, light and dark.
- **Screen readers:** a text summary ("Now 55.3 °C, target 56 °C, at
  temperature since 7:42 PM") and a "Show as table" option.

### 4.8 Accessibility

- **Drawings:** each is `role="img"` with a translated description, built from
  the same view model as the info rows. For example: "Joule in a container of
  water. 55.3 of 56 °C, cooking, 1 hour 12 minutes left."
- **Announcements:** a polite live region announces the changes that matter:
  preheated, ready for food, done, door opened, error and offline.
  Temperature ticks aren't announced.
- **Controls:**
  - they're real buttons and inputs, or carry the matching ARIA roles: switch,
    spinbutton with value text, or radio group;
  - every one is labeled;
  - arrow keys work on steppers and pickers;
  - focus is always visible;
  - the confirm bar takes focus, and Escape cancels it.
- **Colour:** status is never shown by colour alone. The pill always has words.
- **Reduced motion** stops the ripples, the steam and the fan.
- **Checks:**
  - vitest checks roles and labels;
  - axe-core runs on every gallery state, and must report no serious or
    critical violations;
  - a keyboard-only run of the full flow in Playwright.

### 4.9 Unit tests

- View models against the fixtures (§7): status pill, info rows, display,
  preheat, countdowns, lock text and drawing descriptions.
- Preset filtering and formatting.
- Chart data built from history rows.
- Route parsing and the one-appliance rule.
- Languages have the same keys.

## 5. Drawing catalog

### 5.1 Sources

These are research only and kept out of the repo: Breville's product pages and
manuals, and retailer photos.

- **Joule:**
  - 11 in (279 mm) tall and 1.85 in (47 mm) across;
  - a white polycarbonate body with a polished stainless cap and foot;
  - a stainless button on top, and a multicolour LED on the cap's front;
  - a black outlet slot low on the front, a wire clip on the back, and a
    twist-off magnetic foot with an orange pad;
  - no water-line marks (the instruction manual gives 1.5–8 in of depth).
  - Yours is item CS10001.
- **Joule Turbo:** looks the same as the Joule (you, 2026-10-25), 12.28 in
  (312 mm) tall, with MAX and MIN marks on its body. It's sold as "Polished
  Stainless Steel" (BSV600PSS1BNA1).
- **Oven:**
  - 21.4 × 17.3 × 12.7 in;
  - 6 independent quartz elements;
  - two reversible wire racks, giving 8 rack positions;
  - accessories: a 13-inch pizza pan, a 9 × 13 in broil rack and enamel
    roasting pan, and an air fry and dehydrate basket;
  - two finishes: brushed stainless (BOV950BSS1BUS1, CityDweller's) and black
    stainless (BOV950BST1BUS1).
- **Confirmed in phase 0** (the BOV950 instruction book and Breville's renders):
  - the control panel runs down the right: the display at the top; the small
    CONFIRM dial beside START|STOP; the TEMP and TIME dials; buttons for the
    light, convection, A bit more, frozen food and a favorite;
  - the display is pale (brushed stainless) or black (black stainless) while
    idle, and lights orange while the oven runs. The manual documents no "End"
    message, so the drawing's display says "Done";
  - rack position 1 is the top and 8 the bottom: four slots, and a reversible
    rack gives two heights in each. The book places toast and bagel at 4 and
    proof at 8;
  - one light, on the cavity's left wall, on when the door opens or its button
    is pressed;
  - the black stainless model's crumb tray front is orange.
- **Still inferred:** the six elements' split. The BOV900's is three across the
  top and three across the bottom, which the drawing follows.

### 5.2 Sous vide (CSJ100, BSV600)

- **Scene:** the circulator is clipped to the back of a clear container, about
  two-thirds full, seen from a little above, with the part under water seen
  through it. The Joule Turbo is drawn taller, with its MAX and MIN marks; the
  Joule has none.
- **Water:**
  - still while idle;
  - circulation ripples while running;
  - steam as it heats, stronger near boiling;
  - a warm tint that follows the temperature.
- **Food bag:** in the water from the moment the food goes in until Done. It
  holds a steak by default.
- **LED:** lit while a cook runs.
- **Errors:**
  - low water draws the water near the floor, with an amber badge;
  - tipped over draws the circulator on its side;
  - other errors show a red badge.
- **Readouts:** the water temperature on the container, plus the target while
  it heats.
- **Offline:** desaturated, with the LED off.

### 5.3 Oven (BOV950)

- **Body:** the finish material, the door glass with the cavity behind it, the
  handle, the feet, and the control panel on the right.
- **Control panel:** the display is drawn as the BOV950's LCD, measured on
  Breville's close-up: the list of functions with an arrow at the mode, the
  temperature and time in seven-segment digits, convection, the rack position
  and PRESS START, the unlit segments faint. It sleeps while the oven is idle;
  it's pale (black on black stainless) while it waits for Start and once the
  cook is done ("donE"), and orange while the oven runs. A setpoint under the
  mode's lowest (the oven reports 0 °C while it waits) leaves the digits blank.
  The other controls are static, as measured: spun-metal dials, CONFIRM's
  orange ring (lit while the oven is awake) and START's red one (lit while it
  runs, pulsing while it waits for Start).
- **Cavity:** the convection fan cover on the back wall, racks at the mode's
  position, and the elements top and bottom.
- **States:**
  - **Idle:** previews the next cook: its rack and accessory, with no food and
    no glow. Changing Mode updates the preview.
  - **Preheating and Ready for food:** the empty accessory, with the elements
    glowing.
  - **Cooking:** the food in the accessory.
  - **Done:** the elements stop glowing, and the display turns pale and reads
    "donE" in its segments, the card's readout "Done" (the instruction book
    documents no "End" message).
  - **Waiting for Start:** the display is white too, and START's red ring
    pulses.
- **Door:** when it's open, the door drops open and the cavity lights up.
- **Fan:** turns slowly with convection On and fast with Super. Reduced motion
  shows it still.
- **Elements:** glow while the heater preheats or heats. Which elements glow
  follows the mode, since the oven doesn't report it:

| Mode | Rack | Accessory | Food | Elements |
|---|---|---|---|---|
| Bake | 6 | roasting pan | croissants, as in Breville's own pictures | top and bottom |
| Bottom bake | 6 | roasting pan | casserole | bottom |
| Gentle broil ("Crispier air fry" in the app) | 6 | air fry basket | fries | top |
| Roast | 6 | broil rack in the pan | whole chicken | top and bottom |
| Broil | 1 | broil rack in the pan | steak | top |
| Bottom broil | 1 | broil rack in the pan | steak | bottom |
| Outer top broil | 1 | broil rack in the pan | steak | outer top |
| Middle top broil | 1 | broil rack in the pan | steak | middle top |
| Windy broil | 1 | broil rack in the pan | steak | top, with the fan |
| Air fry | 3 | air fry basket | fries | top, with the fan on Super |
| Pizza | 7 | pizza pan | pizza (frosted when Frozen is on) | bottom and top |
| Cookies | 5 | roasting pan | cookies | top and bottom |
| Reheat | 4 | wire rack | plated leftovers | top and bottom |
| Slow cook | 8 | covered pot | — (lid on) | bottom, low |
| Proof | 8 | wire rack | bowl of dough | bottom, low |
| Warm | 4 | wire rack | covered dish | low |
| Dehydrate | 3 | air fry and dehydrate basket | fruit slices | low, with the fan |
| Toast, bagel* | 4 | wire rack | bread or bagel halves | top and bottom |
| Crispy reheat* | 4 | wire rack | pizza slice | top and bottom, with the fan |
| Keep warm* | 4 | wire rack | covered dish | low |

\* These can only be started on the oven; the panel draws them when the oven
reports them.

### 5.4 Built-in presets

Checked in phase 0 (2026-10-25) against these sources:

- **Douglas Baldwin's pasteurization tables** (1 in, 25 mm thick, from 5 °C):
  poultry takes 1¼ h at 63 °C and 55 min at 65 °C, and pork 1½ h at 60 °C.
  The chicken breast and pork chop presets take 2 h, which covers pieces up to
  about 1⅓ in (35 mm). Beef takes
  2¼ h at 56 °C, so the steak presets don't pasteurize; that's normal for
  intact steaks, whose inside is sterile. Below 55 °C he serves food within
  4 hours; the presets' 2½ h limit is stricter. He pasteurizes fish at 55–60 °C
  for longer than these presets, so all three seafood presets carry the
  raw-safe note.
- **The FDA Food Code's whole-roast table** (3-401.11(B)) holds 56.1 °C
  (133 °F) for 56 minutes; the beef roast's 6 hours covers it once the centre
  is up to temperature.
- **USDA FSIS** gives single temperatures instead: 145 °F (62.8 °C) with a
  3-minute rest for beef and pork, 165 °F (73.9 °C) for poultry, 145 °F for
  fish. Sous vide replaces these with time at a lower temperature, which the
  README must say plainly, along with the 1 in thickness the times assume.

The values below are the checked ones.

- **Sous vide sources:** the USDA FSIS time and temperature tables for whole
  cuts, Douglas Baldwin's sous vide tables, and the FDA Food Code.
- **Oven sources:** the mode defaults in `OVEN_MODES`.
- **Safety rule:** below 54.5 °C (130 °F), a preset cooks for at most
  2 hours 30 minutes. Seafood below the FDA Food Code's 63 °C (145 °F)
  carries a note to use fish that's safe to eat raw.

Sous vide (both Joules):

| Preset | Temperature | Time |
|---|---|---|
| Steak, rare | 52 °C (126 °F) | 1 h 30 min |
| Steak, medium-rare | 56 °C (133 °F) | 1 h 30 min |
| Steak, medium | 60 °C (140 °F) | 1 h 30 min |
| Steak, well done | 70 °C (158 °F) | 1 h 30 min |
| Beef roast | 56 °C (133 °F) | 6 h |
| Short ribs | 57 °C (135 °F) | 48 h |
| Pork chop | 60 °C (140 °F) | 2 h |
| Pulled pork shoulder | 74 °C (165 °F) | 24 h |
| Chicken breast | 63 °C (145 °F) | 2 h |
| Chicken thighs | 65 °C (149 °F) | 2 h |
| Salmon (with the note) | 50 °C (122 °F) | 45 min |
| White fish (with the note) | 55 °C (131 °F) | 30 min |
| Shrimp (with the note) | 57 °C (135 °F) | 30 min |
| Soft eggs | 63 °C (145 °F) | 45 min |
| Vegetables | 85 °C (185 °F) | 1 h |

Oven:

| Preset | Mode | Temperature or level | Time |
|---|---|---|---|
| Frozen fries | Air fry | 205 °C / 400 °F | 20 min |
| Chicken wings | Air fry | 205 °C / 400 °F | 25 min |
| Frozen pizza | Pizza, Frozen on | 205 °C / 400 °F | 16 min |
| Fresh pizza | Pizza | 230 °C / 450 °F | 12 min |
| Roast vegetables | Roast | 205 °C / 400 °F | 30 min |
| Roast chicken | Roast | 205 °C / 400 °F | 1 h 15 min |
| Cookies | Cookies | 175 °C / 350 °F | 11 min |
| Cake | Bake | 175 °C / 350 °F | 35 min |
| Leftovers | Reheat | 165 °C / 325 °F | 15 min |
| Salmon fillets | Broil | High | 8 min |
| Dried fruit | Dehydrate | 57 °C / 135 °F | 8 h |
| Bread dough | Proof | 29 °C / 85 °F | 1 h |
| Pot roast | Slow cook | Low | 8 h |

Presets don't set Keep warm or Start timer automatically. Those stay as they
are.

## 6. What each kind shows

Entity keys are the integration's own: `sensor`, `number`, `select`, `switch`
and `button` translation keys.

### Sous vide (Joule, Joule Turbo)

- **Drawing:** §5.2.
- **Pill priority:**
  1. Offline;
  2. Error, in the Error sensor's words;
  3. Updating;
  4. Preheating NN%;
  5. Ready for food;
  6. Cooking;
  7. Done;
  8. Idle.
- **Info rows:**
  - "Target 56° · Now 55.3°";
  - "Time left 1:12 · Ends 8:42 PM", or "Holds until stopped";
  - when Ready for food: "Add the food, then press Continue".
- **Entities:** `status`, `current_temperature`, `time_remaining`, `cook_end`,
  `cooking`, `problem`, `error`, `target_temperature`, `cook_time`, `cook`,
  `auto_start_timer`, `continue`, and the new `preheat`.

### Oven

- **Drawing:** §5.3.
- **Display:**
  - the temperature while preheating;
  - the time left while cooking;
  - "End" once done;
  - "Off" while idle.
- **Pill priority:**
  1. Offline;
  2. Error;
  3. Door open, while a cook is open;
  4. Press Start on the oven;
  5. Preheating NN%;
  6. Ready for food;
  7. Cooking;
  8. Done;
  9. Keeping warm;
  10. Idle.
- **Info rows:**
  - "Air fry · 400 °F · Super convection";
  - "Time left 12:30 · Ends 8:42 PM";
  - while idle or preheating, "Rack 3 · Air fry basket", so it's clear where
    the rack goes.
- **Entities:** the sous vide ones, plus `oven_mode`, `convection`, `level`,
  `keep_warm`, the new `frozen`, `door` and `active_mode`.

## 7. Testing and verification

- **Fixtures** go in `tests/fixtures/panel/*.json`, shared by pytest and the
  frontend. Each holds only entity states and panel messages, with nothing
  personal. `tests/test_panel_fixtures.py` writes them from the real
  integration (`UPDATE_PANEL_FIXTURES=1`) and fails when one drifts. The
  frontend's demo page (`frontend/gallery/panel.html`) runs the real panel on a
  stand-in `hass` built from them, for screenshots and the axe-core run. They
  come from:
  - **the Joule:** your probe captures, redacted;
  - **the oven:** CityDweller's three rounds of diagnostics. They cover bake
    and air fry, in °F:
    - idle and waiting for Start;
    - preheating and ready;
    - cooking, and paused with the door open;
    - finished and stopped;
  - **the Joule Turbo:** the app's state layout only, since nobody has a real
    one.
- **Visual loop:** Playwright renders the gallery in Chrome. I review the
  screenshots and refine each drawing before moving on.
- **Style checkpoint:** you sign off on your Joule in its container and on the
  oven in bake, in light and dark and in a few states, before the rest are
  drawn.
- **Gallery review:** you review every drawing before the docs.
- **End to end:** the demo Home Assistant used for the README screenshot (real
  Home Assistant running the integration against a stand-in cloud) runs the
  panel with fixture states. It's used for the full-flow check and the README
  screenshots.
- **Your Joule,** before the version bump:
  - You install the branch build: unzip a zip built from the branch into
    `/config/custom_components/breville_cooking`, then restart.
  - Then work through this checklist:
    - preheat, ready, Continue, cooking, done, stop;
    - a built-in preset, and a custom one: save, rename, delete;
    - the chart;
    - Celsius and Fahrenheit;
    - the companion app on a phone;
    - keyboard only;
    - VoiceOver on a Mac or iPhone.
- **After the release:** you ask CityDweller to try it with VoiceOver: the
  overview, the oven's full view, a preset, Start, Continue and Done.

## 8. Phases and release

- **Branch:** all work happens on a `sidebar-panel` branch, so main can still
  ship fixes. 0.07 is already out.
- **Progress (2026-10-25):** phases 0–3 are built, with rough versions of the
  phase 4 drawings (every mode, the Joule Turbo, black stainless, errors,
  offline) so the style can be judged on them too. The first drawings read as
  cartoons, so both were redrawn from measurements of Breville's photos, as the
  Sub-Zero drawings were from Wolf's: the light across each part, the
  spun-metal dials, the oven's own display segment by segment, the cavity's
  light, the glossy white and polished cap of the Joules, the water. The
  README's screenshots (phase 5) are done: the overview, the oven's full view
  and the Joule's, each in light and dark, shot in Home Assistant 2026.10 with
  a stand-in cloud running a Joule and an oven cook. The panel's text, and the
  integration's errors it shows, are in all nine languages. Next: your style
  sign-off.
- **Shipping it:** merge the branch, then run the Release workflow for 0.08.

| Phase | Work | Checkpoint |
|---|---|---|
| 0 | Research notes, kept out of the repo; `panel_spec.py`; `presets.py` with the preset tables checked against the food-safety sources; fixtures | — |
| 1 | Option, `frontend.py`, `panel_api.py`, presets store and commands, Frozen food and Preheat entities, diagnostics, translations, backend tests | — |
| 2 | Frontend toolchain and CI; shell (routes, the one-appliance rule, areas, theme, languages); card frame; full view with every control; presets; chart; accessibility layer; simple placeholder drawings | — |
| 3 | Detailed drawings: your Joule in its container, and the oven in bake | **Style sign-off** from you, in light and dark and a few states |
| 4 | Joule Turbo; the oven's other modes, accessories, food, elements, fan and door; black stainless; errors and offline | **Gallery review** of every drawing by you |
| 5 | README section and screenshots; the branch build on your Home Assistant | **Real-device checklist** (§7), then merge and release 0.08 |

## 9. Risks and items to verify

- **The oven's details aren't confirmed:** its control panel, how its elements
  split, which end rack position 1 is at, and its interior light. Product
  photos decide them. Which elements glow is inferred from the mode, since the
  oven doesn't report it.
- **Nobody can check the oven's drawing in person.** You don't have one, and
  CityDweller can't see it. Photos and their diagnostics are the check.
- **The Joule Turbo** has no tester and no real data.
- **Finish detection** relies on item numbers and the serial colour code, taken
  from the app and from retailer listings. An unknown code falls back to
  brushed stainless.
- **Presets are cooking advice.** The built-in ones follow published
  food-safety sources, and the README says to follow a trusted guide. Custom
  presets are up to the admins who save them.
- **Settings are shared.** A preset or a setting changed from the panel
  changes the entities for everyone, just as the device page does.
- **Continue on the oven** (send-step, 0.07) isn't verified yet. The panel uses
  the same button.
- **Frontend APIs:** only the documented `hass` object is used. A Home
  Assistant change to `hass.devices`, `hass.areas` or `hass.entities` would
  need an update.
- **Paths:** the panel at `/breville-cooking` and the files at
  `/breville_cooking` must stay different.
- **New toolchain:** the repo gains Node 22+ and `package-lock.json`. Every
  frontend change needs a rebuilt, committed bundle, which CI enforces.
- **Trademarks:** no logos or badges.
