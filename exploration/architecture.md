# Architecture: a durable store between harness and policy

[Tour home](README.md) · Previous: [Concepts](concepts.md) · Next: [Policy](policy.md)

## The framework separates representation, persistence, and selection

The original authors' architecture illustration is useful as a conceptual map:

![Upstream Actor-Gatherer architecture; credit: The Actor-Gatherer Authors](https://raw.githubusercontent.com/ucbepic/actor-gatherer/26286542395552892e977b0249cd31330d004aa8/assets/architecture.png)

The arrows labeled `insert` and `get_context` in the conceptual description
correspond in the implementation to `Manager.insert`, `Manager.read`, and the
server's combined `rewrite` operation. There is no requirement for a remote
Gatherer service: the shipped connection is JSON lines over a local Python
subprocess's stdin/stdout, with SQLite providing shared durable state.

| Component | Owns | Does not own |
| --- | --- | --- |
| `ag/cli/` | Parse `ag` options, choose a gatherer/harness, check contracts, launch the harness. | Context selection. |
| `harness_kit/` | Read harness-specific calls, content pieces, records, terminal state, and tool meanings. | Gatherer policy; this package does not import `ag`. |
| `ag/integrations/harnesses/` | Hook the harness, identify its session, convert its input and the returned context. | SQLite storage and task ranking. |
| `ag/integrations/tools/ag_connection/` | Start the server, correlate request IDs, handle timeouts/restarts. | Semantics of selected context. |
| `ag/ag_harness/server/` | Protocol operations and ordered per-session request lanes. | Harness-native message formats. |
| `ag/ag_harness/manager.py` and `store/` | Event types, persistence, polling, read provenance, provider counts. | Which tasks are relevant. |
| `ag/ag_policies/` | Context policy, task analysis, layout, policy-owned tables. | Tool execution for the user's task. |
| `ag/ag_tools/` | LLM clients, tokenizers, worker launching, logging/notifications. | Application task semantics. |
| `ag_dashboard/` | Browser UI, history inspection, session control, editor. | Replacement for the Gatherer protocol. |

Read the [server contract](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/server/__init__.py#L1-L175),
[Manager](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/manager.py),
and [adaptor contract](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/tools/ag_orchestrator/adaptor.py)
beside this table.

## One ordinary model call, in runtime order

1. The harness is about to send its conversation to its model. A proxy hook
   (Claude/Codex) or plugin callback (Pi/OpenCode) intercepts that boundary.
2. The adaptor's `to_events` produces typed events. The hook supplies the
   gatherer, channel, working directory, and, when available, model limit and
   fixed preamble such as system instructions and tool definitions.
3. `call_ag` validates the adaptor's declarations and sends `rewrite` through
   `AgClient`. The client starts `python -m ag.ag_harness.server` lazily.
4. `Server.rewrite` inserts the events, skipping duplicates, and finds the final
   event's row ID even if that event was already stored.
5. `Manager.read_logged` polls outside sources, invokes the policy, and records
   the returned context's ordered references.
6. The policy assembles context from stored raw events and made items. It may
   adopt an analysis prepared earlier or wait for new analysis when due.
7. The server returns stored-event envelopes and `{"type": "ag", ...}` items.
   `to_messages` converts these into the calling harness's valid input format.
8. The Actor's model runs. Response/record handling preserves answers and other
   session activity; available provider token counts are reported back for
   subsequent budgeting.

Sources: [`call_ag`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/tools/ag_orchestrator/call_ag.py),
[`AgClient`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/tools/ag_connection/ag_client.py),
[`Server.rewrite`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/server/__init__.py#L478-L543),
and [`Manager._context`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/manager.py#L295-L324).

This describes the normal conversation path, not every request a harness makes.
Hooks distinguish compaction, side calls, and other traffic. A failed rewrite
usually means the hook sends the harness's original input, **not** that the
model call is forbidden.

## Storage keeps observations separate from interpretations

By default, a gatherer lives at `~/.ag/gatherers/<name>/`, with
`gatherer.toml` and `context.db`. `AG_HOME` changes the home. Log files live
separately under the home's `logs/`. The location is read at import time by
[`store/paths.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/paths.py),
so set `AG_HOME` before importing the storage modules or launching a process.

| Tables | Owner | Why they exist |
| --- | --- | --- |
| `event_types`, `event_type_properties` | Store | Define event names and optional/required/identifying properties. |
| `events` | Store | Original JSON, readable text, token counts, identity, insertion order. |
| `_made_items` | Store | Exact policy-authored context, separate from observations. |
| `_reads`, `_read_items`, `_preambles` | Store | What was returned, why, in which order, and with what fixed instructions/tools. |
| `_polls` | Store | Last poll time per source. |
| `_withdrawn` | Store | Events a harness took back; retained for history, excluded from ordinary reads until re-sent. |
| `_open` | Store | Local process claims on harness sessions. |
| `tasks`, `cleaned_messages` | Default policy | Segmented tasks, retained rules, and model-cleaned user requests. |
| `_builds`, `_boundaries` | Default policy | Analysis lifecycle and new-task decisions. |

The [shared schema](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/schema.py)
and [policy tables](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/tables.py)
are the source of truth. The protocol also accepts harness/dashboard record
types beyond the eight default policy types. Such records are useful for
inspection; the policy's type groups do not automatically select them.

**Inference:** separating `events` from `_made_items` prevents the policy from
mistaking its own previous summaries for new observations. It also makes it
possible to inspect exactly which raw or generated items a particular read
returned. It is not a complete snapshot of all external files or a proof of
what a remote provider processed.

## Identity is more specific than a content hash

Event identity is the caller's ID **plus identifying properties**. `channel`
identifies; `cwd` describes. The same ID in two channels can be two events.
Re-sending it in the same channel with a changed working directory does not
rewrite the old event. No ID means every insertion is new.

[`operations.insert`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/operations.py#L313-L349)
checks for duplicates before serializing/tokenizing an already-known payload.
The database's unique index still catches concurrent insert races. SQL uses
`ifnull(property, '')` in that index because ordinary SQLite uniqueness allows
multiple NULLs. An ID-less event intentionally retains SQL's non-colliding NULL
behavior. This is a latency optimization grounded in the fact that harnesses
re-send large histories on successive calls.

For reads, matching a property normally includes rows with that property unset.
Thus a channel sees its own raw events and shared no-channel events. The
default policy deliberately queries other channels separately and renders
their information as text; it does not return their raw harness payloads.
See [`rows` and `_filter`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/operations.py).

## Concurrency is local and per session, not globally serialized

[`Lanes`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/server/__init__.py#L660-L812)
queues requests by gatherer and identifying-property values. One lane runs in
arrival order; different sessions run concurrently. Responses can therefore
arrive out of order, matched by protocol request ID. A separate records lane
allows observational record inserts beside a session waiting for a build.

The store caches one connection per database per thread. It enables WAL,
`synchronous=NORMAL`, foreign keys, and an 8-second busy timeout. WAL permits
readers beside a writer; it does not remove SQLite's single-writer constraint.
`NORMAL` avoids a durable disk sync on each transaction, trading some recent
commit durability on power loss for lower overhead. See
[`schema.connect` and `connection`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/schema.py#L328-L378).

`claim_build` uses `BEGIN IMMEDIATE` to prevent two processes from claiming a
fresh build for the same channel simultaneously. Poller watch/poll pairs have
in-process locks. These are different scopes: do not infer a distributed global
lock, atomic filesystem snapshot, or a linearizable multi-agent world state.

## Harness differences are part of the design

| Harness | Integration mechanism | Representation work |
| --- | --- | --- |
| Claude Code | Python HTTP proxy hook | Split messages into blocks; chained stable IDs; continuity after history rewrites; reconstruct roles, tool pairs, and cache markers. |
| Codex | Python HTTP proxy hook | Responses input items; native IDs or content hashes; developer-role Gatherer messages by default; special compaction handling. |
| Pi | TypeScript extension `context` hook | Split/join content pieces; hidden custom Gatherer messages; suppress native compaction while the Gatherer answers, unless explicitly allowed. |
| OpenCode | TypeScript `experimental.chat.messages.transform` plugin | Replace the outgoing message array without rewriting stored history; disable native automatic compaction and pruning unless explicitly allowed. |

Sources: [Claude adaptor](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/claude/adaptor/to_events.py),
[Codex adaptor](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/codex/adaptor/to_events.py),
[Pi setup](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/pi/setup/setup.ts),
[OpenCode setup](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/opencode/setup/setup.ts).

The dashboard is a separate local HTTP server, with server-sent events for live
views and terminal output. It can launch Claude/Codex sessions, expose shells,
change configuration, and save files. Its editor uses Yjs/`pycrdt` documents and
three-way disk merging. The default loopback binding and origin checks should
not be confused with user authentication. See
[`server.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag_dashboard/server.py#L479-L505)
and [`editor.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag_dashboard/editor.py#L1-L36).
