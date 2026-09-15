# Pre-M1 fix: shared Raw Input listener

Follow-up to `critique/M1.md`. That review flagged two issues in
`devices/raw_input.py` / `devices/hid_pedal.py` to resolve before `engine.py`
and multi-device support get built on top of the M1 shape. This document
records what was actually changed, why, and what is still deferred to M2.
Read it before touching `devices/raw_input.py` or wiring `Engine.start()` to
`InputDevice.start()`.

## Finding 1: RawInputSource cannot have two live instances in one process

**Root cause.** `RegisterClassW` and `RegisterRawInputDevices` are
process-global Win32 calls. The M1 code had each `HidPedal` construct its
own `RawInputSource`, so a second `HidPedal` would silently fail to receive
input: `RegisterClassW` fails on an already-registered class name (return
value was never checked), and `RegisterRawInputDevices` for a
usage-page/usage pair already in use does not reliably fail at all - it
typically succeeds and retargets delivery to the newer window, going quiet
on the first listener with no failed API call to catch. That second half
matters for the fix shape: **detecting a bad second registration after the
fact does not work here**, so the fix has to structurally prevent a second
real registration call from ever happening, not check its return code.

**Mechanism chosen.** `RawInputSource` (`devices/raw_input.py`) is now a
ref-counted, multi-subscriber singleton rather than a one-shot listener:

- `start(on_event)` appends `on_event` to an internal subscriber list under
  a lock. `RegisterClassW` / `CreateWindowExW` / `RegisterRawInputDevices`
  only execute on the 0 -> 1 subscriber transition. Every subsequent
  `start()` call just appends its callback and returns - it never reaches
  the Win32 registration calls again, which is what makes this structural
  rather than a "call twice and hope" approach.
- `stop(on_event)` removes that one callback and only tears the window down
  (`PostThreadMessageW(WM_QUIT)`, join, `DestroyWindow`,
  `UnregisterClassW`) on the N -> 0 transition.
- `_handle_input` now fans a `WM_INPUT`-derived event out to every current
  subscriber, each wrapped in its own `try`/`except` + `logging.exception`,
  so one subscriber's exception cannot block delivery to the others. This
  is new because M1 only ever had one callback; it is a direct consequence
  of adding fan-out.

Ownership deliberately stays inside `devices/raw_input.py`, not
`devices/base.py` (enumeration-only, no runtime listener concern) and not
`app.py`/`Engine` (Engine does not exist yet, and this is a Win32-resource
lifecycle problem the composition root should not need to understand).

**Per-caller handle, not the singleton directly.** Callers do not talk to
the shared `RawInputSource` instance by calling its `start`/`stop`
directly, because its `stop(on_event)` needs to know *which* subscriber to
remove and callers (`HidPedal`) call `stop()` with no arguments. Instead,
`shared_source()` returns a `SharedRawInputSource`: a small per-caller
handle with the same zero-argument `start(on_event)`/`stop()` shape a
private listener would have, which remembers the callback it registered so
its own `stop()` removes exactly that one subscriber from the shared
instance underneath. `HidPedal.__init__`'s default `raw_input=` argument
changed from `RawInputSource()` to `shared_source()`; the
`raw_input=` constructor injection point itself is unchanged, so tests keep
injecting a fake directly and bypass the singleton entirely.
`HidPedal.start`/`stop`/`start_learning`/`stop_learning` bodies did not
change.

**Silent-failure fix.** `RegisterClassW`, `CreateWindowExW`, and
`RegisterRawInputDevices` return values are now all checked on the (only
reachable) first `start()` call; a failure sets an internal error and
`start()` raises `RuntimeError`, consistent with the timeout-raise that
already existed in this file. This is deliberately not covered by NFR-4's
fail-soft language ("a bad binding or a failed action logs and continues") -
that NFR is scoped to runtime dispatch of already-configured bindings, not
device-listener bring-up. Listener bring-up failure is closer to the other
half of NFR-4 (survive unplug/replug with reconnect), which implies visible
failure and retry, not silent swallow.

## Finding 2: no queue boundary yet between the OS thread and event consumers

No code changed in `devices/`. `architecture.md`'s concurrency section
already specifies the correct shape (device thread blocks and pushes to a
queue; a separate Engine worker thread drains it, runs chord resolution,
dispatches actions), and there is no `Engine` yet to wire that queue into.
Building it now would mean building it twice.

What *did* change: `InputDevice.start`'s docstring in `core/ports.py`, and
`HidPedal.start`/`_on_raw_event`'s docstrings in `devices/hid_pedal.py`, now
say explicitly that `on_event` must return fast with no I/O or blocking
work. This is more load-bearing after the Finding 1 fix than it would have
been before: a shared `RawInputSource` fanning out to several `HidPedal`s
means one slow `on_event` now stalls delivery to every device sharing that
listener thread, not just one. Document the contract where the fan-out
lives, before `Engine.start()` gets written against it.

No test was added for this - there is nothing to assert yet; the queue
itself is `engine.py`'s job in M2, per the existing architecture doc.

## Test coverage added

- `tests/test_raw_input.py` (new):
  - `test_start_raises_when_register_class_fails` mocks `RegisterClassW` to
    fail and asserts `start()` raises, instead of reporting success with no
    window and no future `WM_INPUT` (the original silent-failure bug).
  - `test_second_subscriber_never_reaches_register_raw_input_devices` is
    the load-bearing regression test. It mocks `RegisterRawInputDevices` and
    drives two subscribers through `start()` on one real `RawInputSource`,
    then asserts the mock's **call count is 1**. A test that only checked
    "no exception was raised" or "a failure return is handled" would not
    have caught the original bug and would not catch a regression either,
    because - per the SME correction above - a second real call does not
    reliably produce a failure return at all. Proving the call never
    happens a second time is the only assertion that actually pins the
    structural fix in place.
  - Both tests construct `RawInputSource` directly (not through
    `shared_source()`), so they exercise ref-counting and registration in
    isolation from the module-level singleton.
- `tests/test_hid_pedal.py`:
  - `FakeRawInputSource` now wraps a `FakeRawInputBus`, mirroring the
    production `RawInputSource`/`SharedRawInputSource` split, and can be
    constructed with a shared bus.
  - `test_two_pedals_sharing_one_listener_each_receive_only_their_own_events`
    puts two `HidPedal`s on one shared fake bus and proves both receive
    fan-out, each only sees its own device's events (path filtering still
    holds under sharing), and stopping one leaves the other's subscription
    intact.
  - Existing tests are unaffected: a bare `FakeRawInputSource()` still
    behaves as a private, single-subscriber fake.

Full suite: `python -m pytest -v` - 9 passed (2 `test_base.py`, 5
`test_hid_pedal.py`, 2 `test_raw_input.py`), before and after this change
(4 passed before; the 5 new/changed tests above account for the rest).

## Explicitly deferred, and why

- **The actual queue boundary** (device thread -> `queue.Queue` -> Engine
  worker thread). Belongs to `engine.py`, which does not exist yet; building
  it now means guessing at Engine's shape. Tracked as M2 day-1 work per
  `architecture.md`, not new design work.
- **`GetTickCount64`-precision timestamps.** `RawInputEvent.timestamp`
  switched from `time.time()` to `time.monotonic()` in this same change
  (cheap, no test impact - existing tests use literal float fixtures), which
  resolves the NFR-1 concern about wall-clock adjustments during a chord
  window. A higher-resolution Win32 tick source was considered and rejected
  as unnecessary: `time.monotonic()` on Windows already has sub-millisecond
  resolution, well inside the ~50ms / ~40ms budgets in NFR-1; there is no
  precision gap left to close.
- Multi-device support itself (Engine actually starting two `HidPedal`s at
  once) is still not built - this change makes it *safe* to build, it does
  not build it. `core/events.py`'s `logical_device_id`'s `#index` suffix
  (NFR-6) was already anticipating this; nothing else exercises it yet.

## Files touched

- `devices/raw_input.py` - `RawInputSource` ref-counting/fan-out,
  `SharedRawInputSource`, `shared_source()`, `RawInputListener` Protocol,
  registration failure checks, `time.monotonic()`.
- `devices/hid_pedal.py` - default `raw_input=` now `shared_source()`,
  updated type hint, `on_event` contract docstrings.
- `core/ports.py` - `InputDevice.start` contract docstring.
- `tests/test_raw_input.py` - new.
- `tests/test_hid_pedal.py` - `FakeRawInputSource`/`FakeRawInputBus`,
  fan-out test.
