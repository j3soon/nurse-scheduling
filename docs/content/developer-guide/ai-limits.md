<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# AI runtime limits and Pi comparison

Normal agent behavior follows Pi v1.0.0 at
[`a13d35a742c6ef8462812a28fbe1d8c8b7431c32`][pi]. Separate defensive limits
protect the hosted service from malformed streams, runaway work, and resource
exhaustion. These limits have substantial headroom for schedule workflows.
They do not determine when normal conversation compaction starts.

The tables show code defaults and fixed bounds. Defensive defaults are constants
in `core/nurse_scheduling/ai/config.py`. Optional overrides appear below.
Environment examples contain the normal deployment settings.
MB and GB use decimal bytes. MiB and GiB use powers of 1,024.
N/A marks a limit or component absent in the pinned Pi implementation.

## Conversation and generation

| Policy | Pi v1.0.0 | This service |
| --- | --- | --- |
| Automatic compaction | Context tokens exceed model window minus reserve | Same. |
| Context usage | Latest valid provider usage plus estimates for later messages | Same. Text estimates do not override valid same-model usage. |
| Output reserve | 16,384 tokens | `AI_COMPACTION_RESERVE_TOKENS=16384` |
| Recent context retained | 20,000 estimated tokens | `AI_COMPACTION_KEEP_RECENT_TOKENS=20000` |
| History summary output | 80% of reserve, limited by model output and available context | Same. |
| Split-turn prefix output | 50% of reserve, limited by model output and available context | Same. |
| Model context window | Supplied by model definitions | Requires positive context-window metadata before generation. |
| Context safety margin | 4,096 tokens | Same. |
| Tool-result text in summary input | Truncated to 2,000 characters | Same. |
| Cumulative file-operation records in summaries | Supported | Read, write, and edit paths are saved separately and appended to each summary. |
| Context overflow recovery | One compact-and-retry attempt | Same, including explicit overflow after partial output and a length stop below the model output limit. Partial tool calls are not executed. Chats and exports label the omitted attempt. |

Each history or turn-prefix section is summarized in one request. Complete,
successful summaries are accepted, including empty text, as in Pi. Summary
failure preserves the original context and does not disable later automatic
compaction attempts in the same run. Compaction skips when the retention
boundary leaves no older messages to summarize.
An immediately repeated compaction skips when the last transcript entry is
already a summary. Summary text is preserved, including whitespace.
A large text estimate clamps requested output to at least one token, as in Pi.
The provider decides whether the request fits. A provider rejection preserves
the original context.
A recovery attempt can summarize a single oversized final input after omitting
the failed response, as in Pi. Manual compaction keeps that input when there is
no omitted recovery attempt.
A split conversation turn can require two summary requests, as in Pi.
Model token limits bound generated text and reasoning.

### Integration differences

Pi's design guides the whole agent. These implementation differences remain:

- The provider adapter uses OpenAI-compatible messages. Fallback estimates use
  characters divided by four, count readable reasoning and tool arguments,
  and include the system prompt and tool definitions. Opaque signatures and
  encrypted replay data do not inflate these estimates. Message serialization
  and image representation differ from Pi's native message format.
- The loop checks context before tool continuations as well as after a final
  response, so growing tool results can be summarized before the next request.
  Manual compaction uses shared run admission, Stop, replay, and persistence.
  It requires an idle chat instead of implicitly stopping an active schedule
  operation. Use Stop before compacting an active chat.
  The UI combines Pi's two ineligible cases into one skipped notice.
- Status messages stay with their user question. They describe the schedule
  workspace and cannot replace the request that starts a conversation turn.
  Summaries from failed or cancelled runs are invalidated because those runs
  discard their temporary workspace.
- Model discovery must supply a positive context window before paid generation.
  Pi supplies model definitions directly. Numeric reasoning settings must leave
  the provider's minimum thinking budget and room for an answer. Invalid settings
  fail before the request, rather than sending a known invalid payload.
- Pi's extension hooks and custom compaction instructions are not exposed by
  this service. HTTP, memory, storage, and runtime bounds below protect the shared
  deployment and can still refuse work at capacity. Manual compaction bypasses
  the active-history quota and summarizes the full retained history, so reaching
  that quota does not prevent reducing it. Shared memory and concurrency limits
  still apply to the compaction request.

## Defensive execution and input bounds

| Limit | Pi v1.0.0 | This service |
| --- | --- | --- |
| Active history characters | N/A | 64,000,000 characters |
| Active history messages | N/A | 100,000 messages |
| Provider response bytes | N/A | 67,108,864 bytes (64 MiB per HTTP attempt) |
| Calls in one model response | N/A | 1,024 |
| Arguments in one tool call | N/A | 4,000,000 characters |
| Tool rounds and calls per run | N/A | 2,000 tool rounds, 6,000 tool calls |
| Parallel tool executions | Parallel by default | `AI_AGENT_MAX_PARALLEL_TOOLS=16` |
| Command deadline | Optional tool timeout, no default | `AI_SANDBOX_COMMAND_TIMEOUT_SECONDS=60`. A tool can request a shorter deadline. |
| Agent run deadline | N/A | `AI_SANDBOX_TURN_TIMEOUT_SECONDS=21600` (6 hours) |
| Default sandbox file read | N/A | 64 MiB. Schedule and ZIP reads use their specific limits. |
| Captured command output | Bounded tail in memory, full output saved to a file | Same. Capture runs inside the sandbox. The model receives at most 2,000 lines or 50 KiB and the full log path when truncated. |
| JSON request body | N/A | 64 MiB, counted before JSON parsing. |
| Schedule YAML | N/A | 16,000,000 bytes (16 MB) |

The provider counts decoded HTTP bytes before buffering SSE lines or parsing
JSON. An oversized or unterminated line cannot bypass the response bound.
The byte budget applies separately to each HTTP attempt.

User messages have no separate character limit. The model context budget bounds
the accepted provider request. The HTTP body bound protects request parsing.

A completed exchange remains available even if its output crosses a history or
memory bound. Further work is refused until capacity is available, or the user
exports the chat and starts another. A refused optimizer review appears in the
chat as a failed review with the same message. Allow memory headroom for output
from every admitted run.

Parallelism applies to independent read-only batches. A batch containing a
mutating tool remains sequential. More slots can help large I/O batches.
Set concurrency according to sandbox capacity.

## Files, service capacity, and optimizer

These components have no corresponding hosted-service quota in Pi.

| Limit | Pi v1.0.0 | This service |
| --- | --- | --- |
| Retained attachments | N/A | 128 files |
| One attachment | N/A | 50,000,000 bytes (50 MB) |
| Active attachment bytes per chat | N/A | 500,000,000 bytes (500 MB) |
| Archived file bytes per chat | N/A | `AI_MAX_ARCHIVE_BYTES=10000000000` (10 GB, including removed files) |
| Generated ZIP and uncompressed contents | N/A | 250,000,000 bytes (250 MB) |
| Live sessions | N/A | `AI_MAX_SESSIONS=1000` |
| Retained text and file bytes in memory | N/A | `AI_MAX_SESSION_BYTES=1073741824` (1 GiB shared across sessions) |
| Concurrent AI runs | N/A | `AI_MAX_CONCURRENT_REQUESTS=4` |
| Session lifetime | N/A | `AI_SESSION_TTL_SECONDS=2592000` (30 days) |
| Optimizer runs per chat | N/A | 1,000 runs |
| Default solve timeout | N/A | `AI_OPTIMIZER_DEFAULT_TIMEOUT_SECONDS=300` |
| Optimizer result bytes | N/A | 64,000,000 bytes (64 MB) |
| Optimizer result cache | N/A | `AI_OPTIMIZER_RESULT_CACHE_BYTES=256000000` (256 MB) |

Shared memory, concurrency, deadlines, and storage must fit deployment capacity.
They remain operator controls, even when legitimate traffic can fill the service.
Raising a count alone cannot provide more CPU, model capacity, or storage.
The default 50 MB attachment bound stays below NGINX's 64 MiB request bound.

## Optional defensive overrides

Normal operation requires none of these settings. Set a positive integer in
`docker/.env` when a legitimate workload needs another bound. Both backend
Compose variants pass these values only when set, using Compose's
[environment resolution](https://docs.docker.com/reference/compose-file/services/#environment).
The service uses its code defaults when an override is absent. Empty, invalid,
zero, and negative values fail startup. Keep attachment bytes plus multipart
overhead below the proxy request bound when changing upload capacity.

| Environment setting | Default | Scope |
| --- | --- | --- |
| `AI_PROVIDER_MAX_RESPONSE_BYTES` | 67,108,864 | Decoded HTTP response bytes per provider attempt. |
| `AI_MAX_HISTORY_MESSAGES` | 100,000 | Active history messages per chat. |
| `AI_MAX_HISTORY_CHARS` | 64,000,000 | Active history characters per chat. |
| `AI_MAX_SCHEDULE_BYTES` | 16,000,000 | UTF-8 schedule YAML bytes. |
| `AI_MAX_ATTACHMENT_FILES` | 128 | Active attachments per chat. |
| `AI_MAX_ATTACHMENT_BYTES` | 50,000,000 | Source bytes per attachment. |
| `AI_MAX_ATTACHMENT_TOTAL_BYTES` | 500,000,000 | Active attachment bytes per chat. |
| `AI_MAX_DOWNLOAD_BYTES` | 250,000,000 | Generated ZIP bytes and total uncompressed contents. |
| `AI_OPTIMIZER_MAX_RUNS_PER_SESSION` | 1,000 | Optimizer runs per chat. |
| `AI_OPTIMIZER_MAX_RESULT_BYTES` | 64,000,000 | Bytes per optimizer workbook. |
| `AI_AGENT_MAX_TOOL_ROUNDS` | 2,000 | Tool rounds per agent run. |
| `AI_AGENT_MAX_TOOL_CALLS` | 6,000 | Tool calls per agent run. |

For failure ordering, persistence, and event behavior, see
[AI Assistant Backend](ai-assistant.md). The environment example and both backend
Compose variants expose the runtime controls. In Compose, the optimizer timeout
follows `OPTIMIZE_DEFAULT_TIMEOUT_SECONDS` so both services share the same default.

[pi]: https://github.com/earendil-works/pi/tree/a13d35a742c6ef8462812a28fbe1d8c8b7431c32
