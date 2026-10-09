# Design Rationale {#design-philosophy}

The browser owns the schedule being prepared. Backend services optimize a
submitted copy or answer questions about a session snapshot. Users can adopt
these services without moving their wider ward workflow into this application.

## Browser ownership

The frontend keeps editable scheduling data in the browser. Optimization and
AI chat send data only when their respective workflows use the backend. See the
[privacy policy](https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md)
for the exact data-handling behavior.

The optimization backend can run with process-local memory for a small
installation or with Redis for shared job storage. AI sessions remain owned by
one process. Optional PostgreSQL storage supports their recovery after restart.
It does not make active session execution interchangeable across processes.

## Choice of Solver

OR-Tools with CP-SAT is the default CPU solver. The project also exposes
experimental solver paths, including PuLP with cuOpt. See the
[solver reference](solvers.md) for supported platforms, runtime controls, and
test coverage.

## Choice of Input Format

YAML provides a readable representation of scheduling requirements. The format
uses camelCase field names. Its schema and scheduling semantics form the
interface between the editor and deterministic optimization.

`NurseSchedulingData` validates the backend schedule format. The frontend
supports a narrower set of values that its editor can represent. AI proposal
validation checks that frontend set before the browser imports an approved
schedule. Keeping YAML readable does not remove the need for typed validation.

## AI execution and approval

The assistant uses a temporary workspace to inspect files and edit a working
schedule. The application keeps credentials and optimizer job ownership outside
that workspace. The backend validates its candidate and presents a proposal
before changing the browser schedule.

Conversation entries are independent of provider wire messages. The context
boundary derives each request and substitutes interruption notes for discarded
workspace claims. A separate session event stream supplies visible activity
and replay to the browser. Model context, displayed output, and recovery entries
serve different purposes and have separate bounds.

See the [AI architecture](ai-assistant.md#architecture) for execution owners,
cleanup ordering, replay, persistence, and the frontend controller.
