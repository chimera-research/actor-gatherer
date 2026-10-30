# Actor-Gatherer: a source-guided learning tour

Actor-Gatherer sits between a coding agent's conversation and its next model
call. It stores what happened, adds information from other sessions and the
environment, and chooses a context that can differ from the history the agent's
harness holds. The agent still solves the task and runs tools; the Gatherer
decides what information the model receives.

This is an independent educational exploration prepared for Chimera Research,
not an integration, a new implementation, or an upstream-endorsed guide.
**The original project is [ucbepic/actor-gatherer](https://github.com/ucbepic/actor-gatherer),
by The Actor-Gatherer Authors.** Its [MIT license](../LICENSE), copyright notice,
package authorship, and upstream links are preserved. The additions in this
directory use the same license.

## Read it at the level you need

| Question | Start here | Approximate time |
| --- | --- | --- |
| What problem does it solve, and what are its features? | [Concepts and behavior](concepts.md) | 10 minutes |
| Which components own which responsibilities? | [Architecture and storage](architecture.md) | 15 minutes |
| How does it actually choose context? | [The proactive policy](policy.md) | 20 minutes |
| Which source should I read, and in what order? | [Source walkthroughs](walkthroughs.md) | 20–30 minutes |
| Can I try the important mechanics without an API key? | [Getting started](getting-started.md), then [offline_lab.py](offline_lab.py) | 10 minutes |
| What was verified, and which claims need caution? | [Evidence and limitations](evidence.md) | 10 minutes |

For a first pass, read Concepts, run the offline lab, and then read Architecture.
For implementation study, continue through Policy and Walkthroughs. The
[upstream README](../README.md) remains the product introduction; the
[upstream reference documentation](../docs/docs.md) describes the full CLI and
extension interfaces. This tour explains the relationships and tradeoffs rather
than duplicating every option.

## Revision and evidence conventions

The inspected upstream revision is
[`26286542395552892e977b0249cd31330d004aa8`](https://github.com/ucbepic/actor-gatherer/commit/26286542395552892e977b0249cd31330d004aa8),
the `main` tip fetched on **2026-10-30**. Its commit timestamp is
2026-10-30 11:44:37 −07:00 (13:44:37 America/Chicago). The package metadata at
this revision says `actor-gatherer` version `0.1.0`; that is not proof that the
PyPI release contains this exact commit.

Source links throughout this tour are pinned to that revision, with function
names and selected line ranges. They do not silently follow future upstream
changes. The original runtime source is unchanged by this exploration.

We use three distinctions:

- **Implemented:** supported by inspected code; an associated test or lab may
  also exercise it. This does not imply that every live provider was tested.
- **Upstream claim:** stated in upstream prose or figures, not independently
  reproduced here.
- **Inference:** a consequence or tradeoff inferred from the implementation,
  not an API guarantee or an author statement.

The [evidence record](evidence.md) lists actual commands, results, and what was
not run. In particular, deterministic tests do not validate LLM judgment or
reproduce benchmark accuracy.

## Five ideas to keep in mind

1. **Stored history is not sent context.** Removing an event from a model call
   does not normally delete it from the SQLite history.
2. **A gatherer is a sharing scope, not necessarily one daemon.** Several local
   processes can open the same gatherer's database. A channel identifies one
   harness session inside it.
3. **Not every decision calls an LLM.** Persistence, polling, notices, request
   sharing, and assembly are largely ordinary code. Boundary detection,
   segmentation, retention extraction, and relevance ranking use a model.
4. **Cross-harness sharing uses text.** Another session's raw Claude tool blocks
   do not get inserted into a Codex conversation. Its requests and selected
   task history become Gatherer-authored context messages.
5. **Availability and fidelity trade off.** On many failures the harness sends
   its original conversation. Summaries and token limits also have important
   exceptions; read the limitations before relying on them.

## Language and scope, verified from the checkout

[pyproject.toml](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/pyproject.toml)
requires **Python 3.11+** and provides the `ag` and `ag-dashboard` console scripts.
The runtime trees `ag/`, `ag_dashboard/`, and `harness_kit/` contain **147 Python
files (29,787 lines)** and **15 TypeScript files (1,339 lines)** at the pinned
revision. The whole tracked repository has 236 `.py` and 22 `.ts` files.
Counts include blank lines and comments; they exclude this tour. This is a
source-file inventory, not GitHub Linguist's byte-based language percentage.

Python owns the CLI, Gatherer, policy, SQLite store, Claude/Codex integrations,
and dashboard backend. Pi and OpenCode use TypeScript plugins. The dashboard
also has substantial HTML/CSS/JavaScript, much of it in `ag_dashboard/page.html`,
and bundled third-party browser libraries. “Predominantly Python” is accurate;
“Python only” is not.

## Fork and publication base

This tour belongs to the verified organizational fork
[chimera-research/actor-gatherer](https://github.com/chimera-research/actor-gatherer).
The initial fork request failed with HTTP 403; the owner subsequently created
the fork and authorized publication. No alternate destination was used.

The publication base is
[`d6d9f6d2a698017e87c12923fcb4be847488f467`](https://github.com/ucbepic/actor-gatherer/commit/d6d9f6d2a698017e87c12923fcb4be847488f467),
the fork's and upstream's `main` when publication resumed. Since the inspected
revision, only dashboard Escape-key handling and its TODO notes changed.
Those changes are preserved; the tour's source references and language counts
remain pinned to the original inspected revision. See the [evidence record](evidence.md)
for the validation and publication history.
