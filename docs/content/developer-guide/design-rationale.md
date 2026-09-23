# Design Rationale

## Browser-Centric Design

Integrating a new system into a production hospital system is a high bar,
and even with internal connections it is still nearly impossible. Open-source
tools or personnel without such connections therefore have almost no
realistic path to integration and use. This system is decoupled from the main
hospital system and deliberately lightweight.

The schedule lives in the browser. Data leaves the local browser only when
the user explicitly triggers optimization on the Optimization page, or uses
the experimental AI chat. Both paths show explicit UI notes on the privacy
considerations.

Running the free hosted servers makes it necessary to log anonymized data
with a short retention period for debugging and to prevent misuse. If that is
unacceptable, users can self-host the backend instead: the Optimization page
can point at their own server, bypassing the free one entirely. The minimal
self-hosted backend runs in memory mode with just a FastAPI server, and no
Redis, Docker, or other infrastructure is required. This keeps the
self-hosting bar low enough for non-technical users. A design where the
schedule lived on a server would have made self-hosting much harder.

## Solver

The project was evaluated across different solvers, and OR-Tools with the
CP-SAT constraint solver works well. A GPU-accelerated solver was also
briefly experimented with, but not investigated further.

CP-SAT modeling is straightforward for this problem. MIP modeling requires
workarounds such as Big-M formulations. Whether MIP modeling is an inherent
limitation for real-world scenarios has not been fully investigated, and GPU
solvers for CP-SAT modeling have not been investigated yet.

## Domain-Specific Language (DSL)

The schedule is described in a domain-specific language (DSL) rather than a
general-purpose format. In the documentation and day-to-day usage, it is
simply referred to as YAML, to keep things straightforward and avoid jargon.

Human readability and ease of editing by hand are prioritized over machine
parsing simplicity.

The YAML format uses camelCase field names, following the conventions of
Kubernetes.

To allow quick prototyping without defining data type classes, the YAML
input is kept intact in memory. Data is extracted explicitly using utility
functions.

## Templates and the Entry Barrier

Creating a schedule from an empty YAML remains a very high bar. The only
schedule created from an empty YAML that is known to be in real-world use was
created by the main developer, and no other person is known to have done so.
Given a YAML of a ward, modifying it for the next month is much easier,
because most rules and preferences are similar and require few or no changes.

This is a known limitation. The entry barrier is being addressed with better
user-side documentation and the experimental AI chat, which can help modify,
debug, and optimize a schedule. The aim is a better UX that lowers the entry
barrier.

## INRC

The [first](https://nrpcompetition.kuleuven-kulak.be/) and
[second](https://mobiz.vives.be/inrc2/) INRC competitions defined a YAML and
constraint format that was a very useful starting point for the first
implementation in 2023. However, the main focus of this project is not a new
or faster optimization solver, but reusing existing building blocks,
building the missing ones, and tackling the real-world problem.

In the first implementation in 2023, working closely with expert nurses, the
INRC format proved not flexible enough for the real-world cases targeted by
the project. The competition rule set is simplified, and the format could not
handle many real-world requirements in complex multi-ward scenarios. The two
main bottlenecks at that point were not the optimizer itself: five or ten
minutes on a decent PC often produced results good enough for real-world
use. They were (a) a format flexible enough, with minimal assumptions, to allow
all kinds of strange real-world requirements, and (b) a decent UI for
non-developer users to fill in their requirements. That experience led to the
2025 milestone of the first GUI and a rather stable YAML format.

Converting the existing INRC or other datasets to the more flexible YAML
format and running benchmarks is technically viable. It is of low priority now, since
the current top priority of the project is tackling real-world problems, and
is left as future work.

## AI Design Choices

The AI features of this project keep the deterministic YAML pipeline at the
center. The experimental AI chat is the only AI surface, and it works
through the YAML intermediate representation rather than producing schedules
or solver code directly. The current design and the alternatives it replaces
are described below.

**The agentic AI chat.** The experimental AI chat is an agentic assistant.
It can interact with the shell, run the optimizer, and inspect results.
Because it keeps the YAML as the intermediate representation, the AI is
useful on both sides of the YAML. It can modify the YAML, write scripts to
handle a custom input format, or write scripts to produce a custom output
format. The YAML is also easily editable by humans through the GUI, so users
can inspect and correct what the AI proposes before anything is applied.

**End-to-end AI scheduling.** Having the AI generate the schedule
end-to-end, without the YAML and solver pipeline, was not pursued. Current
AI models are not yet strong enough to produce a usable schedule end-to-end.
Even if a future leap in AI allows it, that is a less efficient and more
costly way to handle this problem.

**AI-generated solver code.** A more practical alternative is to have the
AI generate the solver code instead of schedule data. That would make the
process a black box and would make it hard for non-technical users to
understand, modify, or adjust the requirements and constraints. This is not
a new idea, see [arXiv:2307.03875](https://arxiv.org/abs/2307.03875) and
[arXiv:2509.22979](https://arxiv.org/abs/2509.22979). Those papers target
users who can read code, while our intended users are nurses and are not
expected to read code.

**Extending the format.** Extending the YAML format is an ongoing effort.
The project works with real-world use cases and keeps an active feedback
loop from real ward usage, so requirements discovered in deployment are
folded into later versions. Revising and extending the format is
developer-side work, not user-side: users are not expected to be
optimization experts or to work in that domain, and they simply want to get
the work done.

**Future directions.** If either AI approach becomes feasible someday, the
AI rollouts can be distilled back into the deterministic code, allowing
similar performance with much less cost and faster execution.
