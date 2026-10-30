# The proactive policy: analyze occasionally, assemble on every call

[Tour home](README.md) · Previous: [Architecture](architecture.md) · Next: [Walkthroughs](walkthroughs.md)

The default policy is `ProactiveContextManager`. Its three main entry points
are `read`, `check`, and `build`. A **read** assembles the next context. A
**check** asks whether the latest user request starts a new task. A **build**
analyzes history and stores an analysis that a later read can adopt.

This distinction matters: “AI-powered Gatherer” does not mean a second agent
reasons over everything before every token the Actor generates. The hook acts
at model-call boundaries, and most reads need no new model analysis.

## The read path has several reasons to change history

This is explanatory pseudocode, not a replacement implementation:

```text
load the channel's conversation and any shared no-channel history
find the latest analysis and the analysis used by the last read
adopt a ready analysis if this is an eligible boundary
assemble raw events, history sections, guide, and outside additions
if a build/check/join is due:
    start it, or use a build already running
    wait according to why it was started
    adopt and reassemble if the analysis becomes ready
if the context still exceeds the configured maximum:
    replace eligible agent steps with database-reference notes
if it still exceeds the maximum:
    log that condition
return context items, provenance references, analysis ID, and size/budget
```

The decisive source is
[`read_within`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L278-L335),
with scheduling in
[`start_due`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L796-L855).

| Situation | Implemented response |
| --- | --- |
| Small history, no join and not over budget | Keep the conversation plus normal Gatherer additions; no boundary check. |
| At a user message, at least `min_context_tokens`, cooldown satisfied | Ask the boundary model; build if it identifies a new task. |
| `build_every_request=True` | Schedule a build at each eligible user request; mainly useful for experiments/tests. |
| Over the context budget, including mid-turn | Start or wait for a build; use a ready build even outside a normal user boundary. |
| New channel and another channel has a ready build | Run a join build ranking other channels' tasks; keep its own history as the running task. |
| Boundary build finished after the initial wait | Adopt on a later call in that same turn when `for_this_turn` recognizes it. |
| Harness compaction | Build with reason `compaction`; the compaction call receives a read-only assembly. |
| External build request, e.g. dashboard History | Start reason `asked`; ordinary adoption rules still apply. |

Thus the blog's append-only-within-a-segment model describes the usual design
intent, not an absolute invariant: budget pressure, compaction, and delayed
boundary builds can switch context mid-turn.

## A build stores analysis before a read renders it

The worker opens a separate store connection. An ordinary build turns history
into turns and tasks, preserves already-finished tasks, and re-segments the
previously open task plus new turns. Task ranges are persisted as event row ranges, not just
transient turn indexes. Oversized tasks may be recursively subdivided, with a
default maximum depth of 3; a single oversized turn cannot be subdivided that
way.

There are two important special paths. A `limit` or `compaction` build makes
the latest user request the running task and segments only the earlier turns;
another such build in the same turn need not segment again. A `join` build
does not segment its own history: it treats that history as one running task
and ranks other channels' tasks. See
[`limit_tasks`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L1043-L1065)
and [`join_build`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L1015-L1032).

Newly finished tasks receive a structured *retention* extraction:

- `object_handling`: how to read, filter, join, edit, or otherwise treat an object;
- `terminology`: a user-defined meaning;
- `metadata`: a fact the user established;
- `carry_forward`: an explicit instruction for later work;
- `cleaned_user_messages`: user requests with supposed boilerplate removed.

This is more specific than a general prose summary. The prompt asks the model
to retain established decisions, not every action the agent happened to take.
Parsing checks structure and types; it does not prove that a retained rule was
actually established or that removed text was only boilerplate. The original
message stays in `events`; cleaned text lives in `cleaned_messages`.

Ranking scores candidate tasks against the last three turns by default. It
uses names, descriptions, and retained-rule scope labels, rather than a vector
index over full tool output. The policy passes `top_n=len(candidates)`, so this
policy asks to order the complete candidate list even though the generic
ranking helper also supports a budget-sized top-N mode. For ordinary builds,
new summaries run beside ranking; ranking is not guaranteed to see the fresh
summary of a task being summarized in that same build.

Sources:
[`build_within`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L950-L1032),
[`segmentation.update` and `segment`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/segmentation.py#L255-L318),
[`summarize.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/summarize.py),
[`ranking.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/ranking.py).

**Inference:** model-based segmentation and ranking can find non-obvious
relationships that lexical matching misses, but introduce cost, latency, and
semantic error. Retaining original event IDs gives a route back to evidence;
it does not automatically correct those errors.

## The returned context uses different levels of detail

`assemble` orders the context as follows: harness preamble events, Gatherer
guide, history sections, retained pinned events from the condensed span, then
the current raw tail. New outside information is placed among or around that
tail, rather than indiscriminately prepended on every call.

After a build is adopted, its sections are:

| Section | Selection/detail | Default content budget |
| --- | --- | ---: |
| Every earlier request | Earlier user requests, then other channels' indexed requests; can use model-cleaned text. | 30,000 own + 10,000 parallel tokens |
| Earlier messages | Whole recent older tasks, newest first for selection, displayed in history order; messages only. | 15,000 |
| Related earlier tasks | Ranked tasks not already selected as earlier messages; messages only, with task headers/retained rules. | 15,000 |
| Previous task | Immediately preceding task, with tool activity, fitted to its budget. | 15,000 |
| This task so far | Earlier steps of the running task when a cut inside it is necessary. | 15,000 |

The request index stops before requests already covered by the previous/earlier
sections; the heading is not a literal promise that every past request appears
in that one section. `every_earlier_request` can emit an omitted-range note,
and `clip` can remove the middle of a section. “Previous task in full” means
tools are eligible, **not** that every byte is always sent.

The six content budgets total 100,000 tokens; condensed-span pinned events get
another 5,000. The default maximum is 200,000, with a 15,000 minimum for boundary
checks. These are policy defaults, not a universal model window. Config
validation rejects budgets plus pinned allowance greater than or equal to the
maximum, and a minimum greater than or equal to the maximum.

Sources: [`layout.build_sections`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/layout.py#L286-L322),
[`layout.every_earlier_request` and fitting](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/layout.py#L150-L246),
[`tools/render.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/tools/render.py),
and [configuration defaults](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/config.py).

## Token accounting is not one number

The policy budgets the whole model input it knows about, including history
preamble, guide, section overview, and `Read.fixed_tokens` for system/tool
definitions. `Context.tokens`/`_reads.est_tokens` instead describe the part the
policy arranges, excluding those fixed portions. `_reads.sent_tokens` estimates
everything sent; `real_tokens` records a provider-reported count. Comparing
`est_tokens` directly with a provider's total can therefore be misleading.

Default tokenization uses `tiktoken`'s `o200k_base`, with a characters/4 fallback
if loading/encoding fails. Opaque reasoning items can start at zero estimated
tokens; that does not mean the provider charges zero for them. Claude/Codex
counting machinery can update event, made-item, preamble, and total counts.
Exact counting depends on the upstream endpoint and harness path.

When a harness supplies a limit and the gatherer has not explicitly set its
own maximum, `within_limit` targets 90% of that limit. Below the policy default,
the section budgets and minimum shrink proportionally. Above the default, the
maximum rises but the section budgets do not. An explicitly supplied maximum
or complete config object wins over this adaptation.

See [`Read` and `Context`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_interface/policy.py#L41-L88),
[`assemble`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L337-L399),
[`within_limit`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/config.py#L232-L252),
and [tokenizer](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_tools/tokenizers/tiktoken_tokenizer.py).

**The maximum is not an unconditional guarantee.** `stubbed` preserves user
messages and replaces eligible agent steps, keeping tool calls/results grouped.
An unshrinkable user message or fixed preamble can still exceed the budget.
`read_within` explicitly logs and returns if its last-resort assembly remains
too large. The [offline lab](offline_lab.py) demonstrates this edge case with a
deliberately simple counter; it does not make a paid model call.

## Background work can still block a model call

Builds move expensive analysis to worker processes, but the reader may wait:

- `sync_seconds=15` is the normal initial wait.
- If a boundary check finds a new task, the deadline can extend to
  `build_wait_seconds=45`, measured from the start of the wait.
- Over-limit builds and joins may wait up to `build_timeout=3600` seconds.
- The Python client's default response timeout is 300 seconds; it can stop
  waiting before the policy's maximum wait ends.

These are configured ceilings, not measured latency guarantees. “Background”
does not mean free or invisible latency. A ready build is normally adopted at
a user boundary. Most ordinary builds are rejected if their sections are no
smaller than the history they replace; `join` and `compaction` bypass that test.

Build status is `running`, `ready`, `failed`, or `nothing`. Adoption is recorded
by `_reads.basis`, not a fifth `adopted` status. The claim transaction protects
against duplicate fresh builds; a timed-out claim allows a subsequent one.
See [`choose` and `adopt`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L694-L764),
[`wait`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/policy.py#L912-L935),
and [`claim_build`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_policies/proactive_context_manager/tables.py#L202-L223).

## Failures degrade in different ways

| Failure | Source behavior | Consequence |
| --- | --- | --- |
| Boundary model gives no usable verdict | `check` treats it as continuation. | May miss a useful context switch. |
| Every segmentation call is unusable | Build is marked failed; old analysis can remain in use. | No new semantic condensation. Partial per-window failures can use placeholders. |
| Retention extraction is malformed | Parser returns empty retained lists/cleaned messages. | The raw event survives, but useful rules may not be extracted. |
| Ranking is missing/partial | Unranked candidates follow in candidate order. | Still selects context, without a reliable relevance ordering. |
| Poller raises | Skip it; do not advance its successful-poll mark. | Model call proceeds without fresh outside information. |
| Adaptor/server rewrite fails | Return no replacement context and a diagnostic note. | Harness generally sends its original history. |

The failure behavior is intentional availability-oriented design. It is
particularly important for OpenCode: its plugin disables native automatic
compaction/pruning independently of whether a particular rewrite succeeds.
Pi's cancellation is conditional on the Gatherer answering. Read the specific
plugin before assuming every harness has identical fallback behavior.
