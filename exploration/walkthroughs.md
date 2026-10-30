# Source walkthroughs: follow the data, then the decisions

[Tour home](README.md) · Previous: [Policy](policy.md) · Next: [Getting started](getting-started.md)

All source links below refer to upstream
[`26286542395552892e977b0249cd31330d004aa8`](https://github.com/ucbepic/actor-gatherer/commit/26286542395552892e977b0249cd31330d004aa8).
Read these routes with the source open beside the explanation. The questions
at the end of each route test the mental model, not memorization of names.

## 1. Follow one rewrite from a harness to the store

Start with [`call_ag.py:call_ag`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/tools/ag_orchestrator/call_ag.py#L38-L117).
It receives harness messages, identifying properties, an adaptor, and a client.
It adds `cwd`, checks declared properties, calls `to_events`, validates the
event types, and sends a protocol request. It validates the answer before
calling `to_messages`. Optional `out` captures provenance/count information
needed by the hook after the model call.

The wire event names its type as a **string**, whereas `Manager.insert` takes
an `Event` with a **numeric registered type ID**. The server resolves that
boundary; the policy does not parse Claude or Codex requests.

Follow [`Server.rewrite`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/server/__init__.py#L477-L539)
into [`Manager._context`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/manager.py#L295-L324).
The Manager polls, records fixed preambles, constructs `Read`, invokes the
policy, and records the returned `Context.refs`. The return path converts
references into event envelopes or Gatherer-authored `ag` messages.

**Decision to notice:** context replacement is availability-oriented. A failed
conversion or null context gives the hook a reason to retain the original
messages. It is not a transactional promise that “if the rewrite fails,
nothing was stored”: inserts precede the context read and can already have
committed.

Also distinguish **read-only assembly** from a read-only protocol operation.
`Manager.context_only` copies the database into memory, disables jobs while
assembling, and discards the copy. But `Server.rewrite(read_only=True)` still
inserts incoming events first; `compacted=True` can also trigger a build.
The `context` protocol operation therefore does not mean “no database writes
anywhere.” The [lab](offline_lab.py) tests the narrower Manager guarantee.

Read the existing checks in
[`test_call_ag.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_call_ag.py),
[`test_server.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_server.py),
and [`test_suggestions.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_suggestions.py).

**Check your understanding:** why can a dashboard show an event from a call
whose rewrite failed? Because insertion and successful context selection are
different operations with different failure points.

## 2. Learn why a repeated request does not duplicate the whole history

Read [`Event` and `Property`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_interface/event.py)
before [`operations.insert`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/operations.py#L313-L349).
The insert path checks event shape and properties, recognizes a known stable
identity, and returns `None` for an already-stored item. The first payload and
its descriptive properties remain. For a new item it serializes/counts and
inserts; the database uniqueness constraint is the final race guard.

The schema builds the identity index from properties marked `identifies`.
`channel` belongs there, `cwd` does not. This preserves identity when a session
changes directory and re-sends earlier messages. `None` IDs intentionally do
not deduplicate. The four-row identity example in the lab exercises all three
cases rather than relying on a single successful insert.

**A read is not a raw SQL dump.**
[`operations.rows`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/operations.py#L406-L429)
also collapses repeated `event_id`s within its matching set unless `differ`
is supplied. This handles an item imported without properties and later
re-sent with them. Consequently, a broad `rows()` is not the right way to
count distinct physical events across channels with coinciding IDs. Use a
channel filter for a session view, or SQL for a physical row inventory.

Next read [`record_read`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/operations.py#L469-L493).
Each context item has exactly one origin: an `events.row_id` or a
`_made_items.made_id`. `_read_items.position` preserves its order. This is
why “what was stored?” and “what did this call receive?” are separate useful
debugging questions. See
[`test_store.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_store.py)
and [`test_withdrawn.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_withdrawn.py).

**Check your understanding:** does changing a duplicate event's text update
history? No. An observation's identity is not an upsert key.

## 3. Separate producing an analysis from adopting it

Read these in order:

1. [`read_within`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L278-L309):
   load history and build state, choose, assemble, schedule/wait, possibly
   reassemble, then apply the over-budget fallback.
2. [`start_due`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L796-L855):
   distinguish join, over-limit build, explicit per-request build, and
   boundary check. `jobs=None` exits here without model work.
3. [`build_within`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L950-L1032):
   segment turns, store tasks/retention/cleaned requests, rank candidates,
   compute the raw-tail cut, and mark the build ready.
4. [`choose` and `adopt`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L694-L764):
   decide whether that ready build is eligible now and whether its sections
   are smaller than the history replaced.
5. [`assemble`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L337-L399):
   place preamble, guide, made sections, pinned events, raw tail, and outside
   information into one ordered context.

**Decision to notice:** `_builds.status=ready` does not mean the Actor has used
it. `_reads.basis` is the record of adoption. This separates expensive analysis
from the boundary at which changing context is worthwhile. It also explains
why a worker can succeed without immediately changing the next visible read.
The usual smaller-context check has exceptions for join and compaction.

For the model-facing algorithms, read
[`segmentation.update`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/segmentation.py#L300-L318),
[`summarize.parse_retention`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/summarize.py#L153-L187),
and [`ranking.rank`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/ranking.py#L118-L148).
They validate and repair structural outputs, not semantic truth. Ranking
appends candidates omitted by the model in their existing order, preserving a
usable result even when no ranking parses.

The scripted model in
[`test_core.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_core.py)
is a good way to study orchestration without confusing it with model quality.
Also inspect
[`test_join.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_join.py)
and [`test_whole_context.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_whole_context.py).

**Check your understanding:** why can a section omit tool output even though
the database has it? Some sections deliberately select messages only; each
section also has a separate rendering budget.

## 4. Follow a real file change all the way to a warning

[`Manager.poll`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/manager.py#L208-L282)
gives the poller the raw-history texts. In
[`file_changes.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_pollers/file_changes.py),
follow `names_in` → `mentioned_files`/`resolve` → `changed_files` → `poll`.
This is path extraction and `stat`, not a recursive filesystem crawl or file
content diff. Existing files below the root are candidates; deleted files
and final symlink paths are skipped. Parent-directory symlinks are not a
general containment/security guarantee.

The poll timestamp is taken before the poll runs. A 0.05-second lookback
compensates for coarse modification-time resolution, and deterministic event
IDs make repeated reports harmless. Caps bound the watched and changed-file
sets; that also means coverage can be incomplete. The initial poll establishes
a mark and produces no updates.

Then read [`notices` and `own_change`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L598-L690).
An eligible notice needs the current session's prior **tool call**, in the
retained raw context, naming the file. A user message naming it alone is not
enough. Calls that plausibly wrote the file suppress notices for the Actor's
own changes. This is heuristic command interpretation, not causal attribution.

**Decision to notice:** the poller records observations independently of the
policy that decides whether this Actor needs a warning. Other channels can
react differently to the same update. The Actor still has to obey the notice;
the framework does not replace stale tool output with new file contents.

Inspect [`test_pollers.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_pollers.py)
and [`test_outside_events.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_outside_events.py).
The offline lab includes a changed, previously read file and an unrelated
changed file as a negative control.

**Check your understanding:** is a missing warning evidence that a directory
has not changed? No: the poller and policy both deliberately filter updates.

## 5. Compare two adaptors instead of assuming a universal chat format

In [`codex/adaptor/to_events.py:item_id`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/codex/adaptor/to_events.py#L61-L90),
Codex's native nonempty ID wins; otherwise the adaptor hashes sorted JSON.
The explicit tradeoff is that two identical ID-less items become one. Opaque
reasoning blobs start with a zero estimate because their encoded size is not
a measure of reasoning-token cost.

Claude needs a different solution. Its adaptor splits content blocks and
creates chained IDs, so two repeated pieces can still represent different
events. After a context rewrite or compaction, blindly chaining from the new
request's beginning would assign new IDs to old content. Read
[`Continuity.ids` and `carry_on`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/claude/adaptor/to_events.py#L146-L225):
they find an overlap with stored tail events and continue from it.

The return trip is just as important. Read
[`claude/adaptor/to_messages.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/integrations/harnesses/claude/adaptor/to_messages.py):
`to_messages`, `only_sent_tools`, `join`, and `finish`. They reconstruct roles,
place tool calls/results coherently, handle model-specific system messages,
and preserve eligible cache markers. A correct selection of event rows can
still produce an invalid provider request if reconstruction is wrong.

This explains the architecture's two representations: **native payload for
round-tripping**, **readable text for policy reasoning**. Sharing tasks from
another harness uses rendered text, not foreign provider blocks.

Read [`test_claude.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_claude.py),
[`test_codex.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_codex.py),
and [`test_harness_fixtures.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_harness_fixtures.py).
Fixtures capture specific harness versions; passing them is not proof of
compatibility with every future version.

**Check your understanding:** can you add a harness by renaming its messages
to `user_message` and `tool_call`? Not safely. Stable identities, native
reconstruction, compaction, side calls, token accounting, and session
identification are part of the contract too.

## Where to go after these routes

- **Concurrency:** server `Lanes`, `tables.claim_build`, and
  [`test_server_lanes.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_server_lanes.py).
  Distinguish session ordering from database locking and poller locking.
- **Configuration/extensibility:** `ag/ag_harness/home/`, the CLI harness
  catalog, and the [upstream extension reference](../docs/docs.md).
  Understand construction before adding an interface implementation.
- **Dashboard:** `ag_dashboard/server.py`, `sessions.py`, `editor.py`, and
  `page.html`. It is a local process/file control application as well as an
  inspector; see [the security limitations](evidence.md).
- **Protocol reading without execution:** `ag/ag_harness/server/__init__.py`
  begins with its operations and response shapes. Pair it with the actual
  method body when an operation's name sounds stronger than its guarantee.
