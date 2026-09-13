# Design and Requirements

A GUI tool to remap a multi-button foot pedal (and, by extension, other HID
controllers) to keyboard and mouse actions, with per-application profiles and
button chords. Replaces vendor software the user dislikes.

See `architecture.md` for the class model and `claude-code-brief.md` for the
build plan.

## Goals

- Map pedal buttons to one or more keyboard keys, mouse buttons, text, or program
  launches.
- Record input directly rather than picking keys from a menu.
- Save named profiles and switch between them, manually and automatically by
  active application.
- Treat button chords as first-class triggers.
- Ship as a simple-to-install Windows binary, with the codebase ready to extend to
  macOS and Linux.

## Non-goals (for now)

- Reprogramming pedals that store their mapping on-device. Those are a future
  `InputDevice` implementation, not the v1 path.
- Full support for keyboard-emulating pedals that require exclusive OS-level
  capture on Windows. Deferred; see Risks.
- Scripting or plugin system beyond the fixed `Action` types.

## Key decisions

- Language: Python 3.11+. Packaged with Nuitka to a native binary, wrapped with
  Inno Setup.
- GUI: Tkinter (standard library, light footprint, no extra runtime to bundle).
- OS scope: Windows first, cross-platform-ready. All OS-specific behavior sits
  behind ports. `core` has zero OS imports.
- Device layer: generic. The exact pedal is unknown, so v1 targets raw HID reads
  plus an interactive learn step. Concrete `HidPedal` is the first adapter.
- Libraries: hidapi (device reads), pynput (output synthesis and input capture for
  recording), pywin32 (active window on Windows), standard-library JSON
  (persistence).
- Persistence: versioned JSON.

## Functional requirements

### Phase 0 (MVP): detect, map, record

- FR-1 Device discovery: enumerate connected HID devices and present them so the
  user can select which one is the pedal.
- FR-2 Button learning: an interactive flow where the user presses each pedal in
  turn; the device layer records the distinguishing report signature for each and
  assigns a logical `button_id`. Required because generic HID pedals do not expose
  a clean button map.
- FR-3 Normalized events: the device layer emits `ButtonEvent` (down and up) for
  each learned button.
- FR-4 Binding: a trigger maps to an ordered list of one or more actions. Action
  types: key, mouse button, text, program launch, delay.
- FR-5 Recording: capture keyboard and mouse input into an action list. Two modes:
  auto (reads the next input(s), stops on a short idle or after N events) and
  explicit (start button, then stop button). The executor is suppressed while
  recording.
- FR-6 Live apply: with a profile active, pressing a mapped button performs its
  bound actions.
- FR-7 Persistence: save and load the full configuration, including selected
  device, learned buttons, and bindings.
- FR-8 Resident app: a tray icon runs the engine in the background; a config
  window opens on demand to edit mappings.

### Phase 1: profiles

- FR-9 Create, rename, duplicate, and delete profiles.
- FR-10 Manual profile switch from the tray menu and the config window.
- FR-11 Bindings are stored per profile.

### Phase 2: active-application detection

- FR-12 The active window watcher reports the focused app (executable name and
  window title) on Windows.
- FR-13 Each profile carries ordered match rules (glob patterns on executable or
  title). First match wins; a designated default profile is the fallback.
- FR-14 The active profile switches automatically on focus change.

### Phase 3: chords

- FR-15 The chord resolver collapses presses that begin within the chord window
  into a single chord trigger.
- FR-16 Chords are toggleable globally and per profile, and the setting persists.
- FR-17 A chord is bound exactly like a single button.

## Non-functional requirements

- NFR-1 Latency: press-to-action under roughly 50 ms with chords off. Enabling
  chords adds a bounded, configurable delay (default ~40 ms) by design, since the
  resolver must wait to see whether a second button joins.
- NFR-2 Footprint: modest idle resident cost. Block on device reads rather than
  polling in a busy loop.
- NFR-3 Cross-platform-ready: every OS-specific call lives behind a port
  (`OutputSink`, `ActiveWindowWatcher`, `InputDevice`). Adding a platform means
  adding adapters, not editing core.
- NFR-4 Robustness: survive device unplug and replug with automatic reconnect. A
  bad binding or a failed action logs and continues; it never takes down the
  engine.
- NFR-5 Recording safety: while recording, captured input neither fires mappings
  nor leaks to the focused application.
- NFR-6 Portable profiles: `trigger.device_id` is a logical identifier derived
  from vendor:product (plus a stable index when several identical devices are
  present), not an OS handle. Profiles then survive reconnects and can be shared
  between machines with the same hardware.
- NFR-7 Packaging: reproducible Nuitka build to a native binary, wrapped by an
  Inno Setup installer with a Start menu entry, an uninstaller, and an optional
  run-at-login registration. Document the SmartScreen click-through and the
  antivirus false-positive risk that comes with input-hook heuristics.
- NFR-8 Testability: the core is exercised headless with fakes. Chord timing and
  profile resolution are unit-tested without hardware.

## Persistence schema

Versioned JSON. `version` gates migrations. `device_id` is the logical id from
NFR-6.

```json
{
  "version": 1,
  "default_profile_id": "base",
  "settings": {
    "chord_window_ms": 40,
    "chords_enabled_global": false,
    "run_at_login": true
  },
  "devices": [
    {
      "device_id": "0c45:7403#0",
      "name": "USB Foot Switch",
      "buttons": [
        { "button_id": 1, "signature": "report:03:01" },
        { "button_id": 2, "signature": "report:03:02" },
        { "button_id": 3, "signature": "report:03:04" }
      ]
    }
  ],
  "profiles": [
    {
      "id": "base",
      "name": "Default",
      "chords_enabled": false,
      "match_rules": [],
      "bindings": [
        {
          "trigger": { "kind": "button", "device_id": "0c45:7403#0", "button_ids": [1] },
          "actions": [ { "type": "key", "params": { "keys": ["ctrl", "c"] } } ]
        },
        {
          "trigger": { "kind": "chord", "device_id": "0c45:7403#0", "button_ids": [1, 2] },
          "actions": [ { "type": "launch", "params": { "target": "notepad.exe" } } ]
        }
      ]
    }
  ]
}
```

Notes:

- `signature` is opaque to everything but the device adapter that produced it. It
  is how a learned button is recognized in the raw report stream.
- Bindings store triggers as a list, not a map, so the file is plain JSON. The
  engine builds a `Trigger`-keyed lookup at load time.
- `button_ids` is a sorted list on disk and a `frozenset` in memory.

## Concurrency model

- Device read thread: blocks on hid reads, pushes `ButtonEvent`s to a queue.
- Engine worker thread: drains the queue, runs the chord resolver (holding a press
  up to `chord_window_ms` when chords are on), resolves the profile, executes
  actions.
- Active window watcher thread: polls every few hundred ms, updates `AppContext`
  under a lock.
- GUI thread: Tkinter on the main thread. Cross-thread UI updates go through
  `widget.after(...)`, since Tkinter is not thread-safe.
- `Config` is guarded by a lock and swapped atomically on reload.

## Risks and open questions

- Pedal type unknown. Confirming the vendor:product id lets us finalize
  `hid_pedal.py` and verify it is a raw-HID device rather than a keyboard-emulating
  one. Until then the adapter is written against the generic raw-HID path.
- Keyboard-emulating pedals. If the pedal presents as a keyboard, remapping means
  capturing it exclusively and suppressing its original keystrokes. On Windows
  that is genuinely hard (low-level hooks with suppression, or an interception
  driver) and would expand scope. This is why `InputDevice` exposes grab support
  as a capability rather than assuming it.
- Active-window detection on Linux later. X11 is workable; Wayland is restrictive
  and varies by compositor. The null watcher keeps the app functional meanwhile.
- Packaging heuristics. Because the app installs input hooks and synthesizes
  keystrokes, some antivirus engines flag it. Nuitka's native binary reduces false
  positives versus a self-extracting bundle but does not eliminate them.
