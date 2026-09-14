oNothing foreign here, actually — this is a pretty standard pattern, just with names drawn from a specific tradition. Let me break down what's going on.

The pattern: Ports and Adapters (aka Hexagonal Architecture)

core/ports.py is named that deliberately — "ports and adapters" is a well-known architectural style (Alistair Cockburn, early 2000s). The idea:

Port = an interface the core logic depends on, defined by the core, in the core's own vocabulary (InputDevice, OutputSink, ProfileStore). It says "I need something that can do X" without caring how.
Adapter = the concrete implementation that plugs into a port from the outside (HidPedal, PynputOutputSink, JsonProfileStore in devices/, platform/, persistence/).
This is just dependency inversion (the "D" in SOLID) applied consistently: core defines abstractions, everything else implements them, and the arrow of dependency points inward. That's exactly what CLAUDE.md's "dependency rule" is enforcing — it's the whole point of the pattern, not incidental style.

Why ABCs specifically

InputDevice(ABC) with @abstractmethod is Python's version of an interface. Python doesn't have interface as a keyword like Java/C#, so ABCs are the idiomatic stand-in when you want to force subclasses to implement certain methods (missing one raises at instantiation, not just at call time). This is completely standard, mainstream Python — you'll see it all over the standard library (collections.abc.Sequence, io.IOBase) and any serious Python codebase (Django's Storage, SQLAlchemy dialects, etc.).

Why so many small frozen dataclasses instead of "real" classes

ButtonEvent, Trigger, Action, AppContext are frozen dataclasses, not classes with behavior. That's intentional and it's a different flavor of OOP than what "older industry" code often teaches (Java-style: everything is a class with methods and internal state). This codebase is closer to a functional core, imperative shell style:

Data (Trigger, Action, Profile...) is immutable and dumb — no methods, just fields.
Behavior lives in separate, stateless functions/classes (ProfileResolver.resolve(ctx, profiles), binding_for(trigger, profile)) that take data in and return data out.
I/O and mutation are pushed to the edges (devices/, platform/, persistence/).
Why: it makes the interesting logic (chord matching, profile resolution) trivial to unit test with plain values — no mocks, no setup, just call the function with a Trigger and a list[Profile] and assert on the result. That's exactly what CLAUDE.md's "Purity requirement" section is asking for.

Naming conventions specifically

*Watcher, *Sink, *Store, *Resolver, *Executor — these suffixes are a common convention for naming things by role rather than by implementation. A "Sink" is something you push output into; a "Store" persists things; a "Resolver" takes ambiguous input and picks one answer. It's a naming vocabulary borrowed from patterns like Strategy, Repository, and Observer — you'll see the same suffixes in Java/C# codebases, Go, Rust traits, etc. It's not Python-specific, and it's not new — it's decades old and still how most statically-typed-adjacent architectures name things.
Config, Profile, Binding, Action are just nouns for what they hold — nothing fancy there.
Is this "proper" Python OOP?

There's a real tension in the Python community: some code leans into this Java/C#-flavored style (ABCs, interfaces, DI), and some leans into "Pythonic" duck-typing where you'd just document the expected shape and not bother with an ABC at all, relying on structural typing (Protocol from typing is the more Python-native alternative to an ABC for this exact purpose). Both are legitimate. This codebase chose ABCs + explicit ports, likely because:

It wants abstractmethod's enforcement (fail fast if an adapter is incomplete).
It's aiming for testability with fakes (FakeInputDevice, FakeOutputSink) — swapping a concrete class for a fake behind a shared interface is the classic reason to have the interface at all.
It's going to be compiled with Nuitka and cross-platform later, so explicit interfaces make the seams where platform code plugs in obvious.
So: not "old industry" foreign, and not over-engineered for its stated goals — it's a deliberate, textbook application of hexagonal architecture + functional-core/imperative-shell, expressed with Python's ABC machinery instead of Java-style interfaces. If anything felt unfamiliar, it's probably that combination (small frozen dataclasses + ABC ports) rather than either piece alone.