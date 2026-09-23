# Design Rationale

The project deliberately minimizes the entry barrier to real-world
deployment by keeping the system lightweight and browser-centric, without
requiring integration with a hospital information system. Within the
scheduling pipeline, the DSL provides a stable and inspectable semantic
boundary between human or AI interpretation and deterministic optimization.
AI can help users create, modify, and extend schedules around that boundary
without requiring every optimization run to redefine the meaning of the
scheduling requirements.

## Browser-Centric Design

Integrating a new system into a production hospital system is a significant
adoption barrier, even when internal connections exist. The goal of this
project is to minimize the entry barrier so that hospitals, wards,
researchers, and other users around the world can try and deploy the system
without deep integration with an existing hospital information system. The
system is therefore deliberately decoupled and lightweight.

The canonical schedule is kept in the browser. The frontend sends
scheduling data to backend services when the user explicitly invokes
features such as optimization or the experimental AI chat. See the [privacy
policy](../PRIVACY.md) for the exact data-handling behavior.

Both the frontend and the backend can be self-hosted. The optimization
backend is intentionally simple to deploy: the minimal configuration runs
in memory mode with just a FastAPI server, and requires no Redis, Docker,
or other infrastructure. Keeping the canonical schedule browser-side
substantially lowers the infrastructure and integration requirements.

## Solver

The project has evaluated several solvers, and OR-Tools with the CP-SAT
constraint solver works well for the targeted problems. The project also
briefly experimented with a GPU-accelerated solver, but did not investigate
it further.

CP-SAT modeling is straightforward for this problem. Reproducing the
current CP-SAT constraint and scoring semantics in the project's MIP
implementation requires additional linearizations and auxiliary variables,
and in some cases Big-M-style formulations or equivalent techniques. This
discussion refers to the project's current implementation, not to MIP in
general. The project has not established that the additional modeling
complexity observed in the current implementation is an inherent limitation
of MIP for real-world nurse scheduling. GPU-accelerated alternatives for
comparable formulations have not been investigated in depth.

## Domain-Specific Language (DSL)

The schedule is described using a domain-specific language (DSL),
serialized as YAML. The YAML file is the serialization format, while the
schema and semantics defined by the project form the nurse-scheduling DSL.
In user-facing documentation and normal usage, it is referred to simply as
YAML, to keep things straightforward and avoid jargon.

Human readability and ease of editing by hand are prioritized over machine
parsing simplicity. The YAML format uses camelCase field names, following
the conventions of Kubernetes.

To allow quick prototyping without defining data type classes, the YAML
input is kept intact in memory. Data is extracted explicitly using utility
functions.

## Templates and the Entry Barrier

Several real-world schedules have been created from scratch, but so far
those initial schedules have been created by the main developer together
with domain users. Translating a ward's requirements into the DSL for the
first time is a high initial or bootstrap barrier.

Once an initial schedule exists, it becomes a reusable ward template, and
subsequent monthly schedules are much easier to prepare, because most
constraints and structure remain similar. The recurring maintenance barrier
is much lower than the bootstrap barrier.

Better documentation, GUI support, templates, and the experimental AI chat
are intended to reduce the bootstrap barrier, so that users do not need the
main developer to create the initial schedule.

## INRC

The [first](https://nrpcompetition.kuleuven-kulak.be/) and
[second](https://mobiz.vives.be/inrc2/) INRC competitions provided
benchmark formats and constraint sets that were a useful starting point for
the original implementation in 2023. However, the main focus of this
project is not developing a new or faster optimization solver, but
integrating existing building blocks, developing the missing pieces, and
addressing the practical barriers to real-world use.

Based on the project's experience working closely with expert nurses, the
competition-oriented constraint sets were not flexible enough for the range
of complex real-world and multi-ward requirements encountered by the
project. The optimization runtime itself was often not the primary
bottleneck: five or ten minutes of optimization could already produce
practically useful results. The larger challenges were expressing diverse
real-world requirements with minimal assumptions, and providing a usable
interface for non-developer users to fill in their requirements. That
experience led to the 2025 milestone of the first GUI and a stable YAML
format.

Converting the existing INRC or other datasets to the more flexible format
and running benchmarks is technically viable. It is of low priority now,
since the current top priority of the project is tackling real-world
problems, and is left as future work.

## AI Design Choices

The AI features sit on the boundary described at the top of this page. The
central architecture is:

```text
Human / AI
    ↓
Nurse-scheduling DSL (YAML)
    ↓
Validated deterministic model
    ↓
CP-SAT / other solver
    ↓
Schedule
```

**The agentic AI chat.** The experimental AI chat is an agentic assistant.
It can interact with the shell, run the optimizer, and inspect results.
Because it keeps the YAML as the intermediate representation, the AI is
useful on both sides of the YAML. It can modify the YAML, write scripts to
handle a custom input format, or write scripts to produce a custom output
format. The YAML is also easily editable by humans through the GUI, so
users can inspect and correct what the AI proposes before anything is
applied.

**End-to-end AI scheduling.** The project experimented with and considered
having the AI directly produce schedules, bypassing the YAML and solver
pipeline. In the project's experience, current models are not sufficiently
reliable or efficient for the complex real-world cases targeted by this
project, especially when many interacting hard and soft constraints must be
respected. This approach was therefore not pursued as the main
architecture. Once the requirements are formalized, specialized
optimization remains a better fit for repeatedly solving a well-defined
combinatorial problem.

**AI-generated solver code.** Generated solver code can be inspected and
tested, so it is not simply a black box. The more important distinction is
that generated solver code requires part of the semantic interpretation and
model implementation to be regenerated on each AI run. The current approach
instead gives commonly used scheduling requirements stable, documented, and
tested semantics in the DSL and the deterministic solver implementation.
Generated solver code has a real advantage: it may express a new
requirement immediately, without waiting for the DSL and solver
implementation to be extended. This tradeoff is especially relevant because
the intended users are nurses and other domain users. They should be able
to inspect and adjust requirements through the GUI and the YAML rather than
being expected to inspect optimization code. Natural-language-to-
optimization and model-generation approaches such as
[OptiGuide](https://arxiv.org/abs/2307.03875) and
[OptiMind](https://arxiv.org/abs/2509.22979) illustrate this direction.

**Extending the format.** A predefined DSL cannot immediately represent
every new requirement, while AI-generated formulations could potentially
attempt unsupported requirements dynamically. The project currently accepts
this tradeoff. Real-world deployments provide a continuous feedback loop:
recurring requirements can be identified, and useful patterns can then
become stable, documented, and tested first-class features of the DSL and
the deterministic solver. Extending the format is developer-side work, not
user-side: users are not expected to be optimization experts or to work in
that domain, and they simply want to get the work done.

**Future directions.** AI-generated formulations and experimental solver
code can be treated as a discovery and prototyping mechanism. If certain
patterns repeatedly prove useful in real-world deployments, they can be
incorporated into the deterministic implementation as first-class
constraints or modeling techniques. This gives the project a path to
combine AI flexibility with lower runtime cost, reproducibility, and
testability, while retaining a user-facing representation that does not
require optimization expertise.
