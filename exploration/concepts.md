# Concepts: history, context, and shared awareness

[Tour home](README.md) · Next: [Architecture](architecture.md)

## The problem is deciding what the model should see

A coding harness accumulates user messages, answers, tool calls, and tool
results. Eventually that history is too large or contains too much irrelevant
material. Merely keeping the newest messages can lose an old instruction that
still matters. Merely offering a search tool requires the agent to realize that
it is missing information in the first place.

Actor-Gatherer's implemented intervention is to **rewrite the input to a model
call outside the task-solving agent**. Its default policy can retain raw recent
history, reintroduce selected earlier tasks, and insert notices or another
session's requests. It does not train the Actor or change its model weights.
See [`call_ag`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/tools/ag_orchestrator/call_ag.py#L38-L117)
and [`ProactiveContextManager.read_within`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L278-L309).

## A small vocabulary

| Term | Meaning in this codebase |
| --- | --- |
| Actor | The task-solving harness plus the adaptor that connects it to the Gatherer. |
| Harness | Claude Code, Codex, Pi, or OpenCode: the program that calls a model and runs tools. |
| Gatherer | A named context-management scope with its own configuration and SQLite database. |
| Channel | A session identifier within a gatherer, usually the harness's own session/thread ID. |
| Event | One observed item, with a registered type, opaque JSON payload, optional stable ID, readable text, token count, and properties. |
| Turn | A real user-message event and the events following it until the next user-message event. |
| Task | Consecutive turns serving one objective, as segmentation infers it. Not an executable work queue. |
| Build | A stored analysis of history: tasks, summaries, ranking, and cut position. Not a model answer to the user. |
| Made item | Context authored by the policy, stored separately from observed events. |
| Read | One request for context; the read log records the event it responds to and what was returned. |

The contracts live in [`event.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_interface/event.py),
[`policy.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_interface/policy.py),
and [`tools/history.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/history.py).
The upstream blog also calls tasks *segments*.

## Implemented features and their boundaries

| Feature | What actually happens | Important boundary |
| --- | --- | --- |
| Persistent history | Events and each read's references are kept in SQLite. | Persistence is not unlimited model context, nor an encrypted archive. |
| Long-session context management | A model segments turns, extracts retained rules, and ranks earlier tasks; code renders budgeted sections. | Model judgments and truncation can lose information. |
| Cross-session awareness | Other channels' user requests become contextual messages; selected tasks can enter history sections. | Sharing is within one gatherer; it is not automatic task assignment or file locking. |
| New-session reuse | A new channel can build a context from another channel's ready analysis. | No ready build means no such join build; request sharing still works. |
| Environment awareness | The file poller checks modification times of named files; the policy can tell the Actor to re-read one. | It does not continuously watch or understand every file. |
| Multiple harnesses | Adaptors map harness-native messages into events and back. | Provider-specific message rules still matter; adapters are not interchangeable wire protocols. |
| Inspection and interaction | The dashboard shows sessions, history, returned contexts, and model usage, and can run agents and edit files. | It is a local control surface, not a read-only telemetry page. |
| Extension points | Policies, pollers, adaptors, launchers, LLM clients, and tokenizers have explicit interfaces/configuration. | A new event type is not automatically meaningful to the default policy. |

Sources: the [default policy](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py),
[file poller](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_pollers/file_changes.py),
[harness catalog](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/cli/harnesses.toml),
and [dashboard routes](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag_dashboard/server.py#L1-L129).

## Example 1: another session established a convention

Suppose session B receives “Use CAD for this report,” and session A later
receives “What is the total?” Both belong to gatherer `finance`.

1. B's request is stored with `channel=B`.
2. A's context read loads its own conversation, not B's raw message payloads.
3. `parallel_requests` reads other channels' user-message events and makes a
   contextual note containing B's words and the location of B's history.
4. At A's user-message boundary, the new note goes immediately before A's latest
   request. If it arrives while A is using tools, it goes after A's latest step.
5. Once shown, the note keeps its logical place on later reads. A later adopted
   build may absorb the request into its index instead.

This simple sharing path requires **no relevance-ranking call**. It also does
not transmit every answer B writes as a live message to A. The policy's text
tells A not to take over B's task, but to apply relevant conventions from it.
That is a prompt instruction, not an enforced access-control rule.
See [`parallel_requests`, `parallel_places`, and `shown_before`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L501-L566)
and [the wording](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/config.py#L168-L184).

**Inference:** sessions in one gatherer should belong to a compatible trust and
instruction scope. The implementation assumes the same user's related work;
mixing unrelated clients' or projects' sessions can share inappropriate context.
Different gatherers separate histories by storage, not by a multi-tenant ACL.

## Example 2: a file changed after the agent read it

Suppose A calls a tool to read `prices.csv`. A user edits it before A's next
model call. On that next read, the Manager asks the file poller for changes.
The poller can emit `environment_update`; the policy checks whether A's relevant
tool history named that file and whether the change appears to be A's own
write. If eligible, it adds a notice telling A to re-read the file.

The notice contains **a warning, not the replacement file contents**. The Actor
must still choose to read the file and reason correctly. Polling occurs at
context-read time, so an edit after polling can still race with the model's
action. Neither file mutation nor the Actor's model call is locked by this
mechanism. See [`Manager.poll`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/manager.py#L208-L282)
and [`notices`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L598-L690).

## Example 3: the history becomes too large

The policy can replace earlier history with a request index, selected task
messages, and a more detailed previous task. The current task normally stays
raw. If even that task is too large, a build can move its earlier steps into
“This task so far.” A last-resort path can replace large agent steps with
notes naming their event rows in the database.

This is **context selection, not destructive history compaction**: the original
events remain available for inspection or explicit retrieval. The policy gives
the Actor a database guide, but there is no guarantee that the Actor follows it.
See [the assembly implementation](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L337-L499).

## What this framework is not

- It is not an Actor-model runtime for distributed message passing. “Actor”
  here names the task-solving agent.
- The shipped policy is not vector-database retrieval. It uses SQL history,
  task descriptions, LLM ranking, and deterministic rendering; see
  [`ranking.rank`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/ranking.py#L134-L148).
- It is not a team planner that automatically assigns jobs or reconciles edits.
  The dashboard can launch sessions, but the Gatherer's core job is context.
- It is not a proof that an answer is correct, that a summary is faithful, or
  that all relevant information fits. Those are separate evaluation questions.
