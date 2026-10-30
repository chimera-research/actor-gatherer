# Evidence, limitations, and publication status

[Tour home](README.md) · Previous: [Getting started](getting-started.md)

## Scope and provenance

This exploration inspected the public upstream checkout at
[`26286542395552892e977b0249cd31330d004aa8`](https://github.com/ucbepic/actor-gatherer/commit/26286542395552892e977b0249cd31330d004aa8)
on **2026-10-30**. It followed CLI/config construction, the four harness
integrations, the stdio server and request lanes, Manager/store contracts,
proactive-policy scheduling and assembly, model-facing helpers, file polling,
dashboard routes/editor, existing tests, and upstream explanatory material.
It is a source-guided exploration, not a security audit or a production
compatibility certification.

The original [MIT license](../LICENSE), copyright notice, package authorship
(Sepanta Zeighami in `pyproject.toml`), and upstream links are preserved. The
tour credits The Actor-Gatherer Authors and is not upstream-endorsed. The only
existing file changed is a discoverability note in the root README; additions
live under `exploration/`. Runtime code, tests, package metadata, original
documentation, assets, and license are unchanged.

## What was actually executed

Environment: Linux x64 Amp orb; Python **3.11.6**; Node **26.12.1**. Base package
dependencies were installed into `/tmp/actor-gatherer-explore-venv` with:

```bash
uv venv /tmp/actor-gatherer-explore-venv
uv pip install --python /tmp/actor-gatherer-explore-venv/bin/python -e .
```

These commands ran from the source checkout. No credentials were needed for
the lab or automated tests. The optional `openai-codex` dependency was not
installed for a live Gatherer client.

| Check | Actual result | Interpretation |
| --- | --- | --- |
| `python3 -B -S exploration/offline_lab.py` | Six demonstrations passed; zero LLM calls. | Real SQLite, default policy assembly, and real file polling work for the exercised inputs without site packages. |
| Tutorial's three SQL queries | Executed against a disposable real Manager database; all returned independently expected rows. | Query columns and provenance examples match this schema. |
| `python -m unittest discover -s tests -q`, soft descriptor limit 1024 | 1,286 tests ran; **25 errors**, including file-descriptor exhaustion and SQLite open failures. | The initial full-suite attempt did not pass. |
| Same Python command, unchanged source, after `ulimit -n 8192` | **1,286 tests, OK**, 134.019 seconds. | Existing suite passed with the resource-limit workaround. |
| `node --test --experimental-strip-types --no-warnings tests/ts/*.test.ts` | **43 passed, 0 failed**, about 1.8 seconds. | Existing TypeScript fixture/unit checks passed. |
| Installed `ag --help` | Successful help output. | Entry-point import/dispatch works; not a live harness launch. |
| Repeat offline lab | Ten consecutive runs passed. | The real-file-change demonstration did not require a timing retry in these runs. |
| Guide-reference validation | 134 source/local links checked against the pinned checkout; line ranges, local anchors, and code fences valid. | References resolve; this is not a live availability check of every GitHub URL. |
| `git diff --check` and added-file whitespace check | Passed. | The README change and new tour contain no trailing-whitespace errors. |

The passing Python run used
`PATH=/tmp/actor-gatherer-explore-venv/bin:$PATH` so its subprocesses also found
the installed package. It still emitted an unclosed-socket `ResourceWarning`;
passing assertions do not mean the run was warning-free.

### Why the descriptor workaround is recorded rather than hidden

The inspected `tests/test_core.py:Base` creates a temporary database path per
fixture. Its teardown removes the directory without releasing the
thread-local store connection cache. Repeating three fixture lifecycles,
each opening the store, produced open-descriptor counts **4 → 7 → 10 → 13**;
calling `schema.release()` returned the count to **4**. That directly shows
retained connections in this fixture and supports the diagnosis of resource
accumulation during the suite. It is not proof that every error or warning
has that single cause.

Sources: [`Base.setUp/tearDown`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/tests/test_core.py#L110-L127)
and [`schema.connection/release`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag/ag_harness/store/schema.py#L357-L378).
Fixing upstream fixture cleanup is outside this documentation task. No runtime
or test code was altered to produce the passing result.

### The language inventory is reproducible

Only upstream-tracked files were counted, not installed dependencies,
generated caches, or the tour additions:

| Scope | Python files / lines | TypeScript files / lines |
| --- | ---: | ---: |
| Whole upstream checkout | 236 / 55,359 | 22 / 1,960 |
| `ag/`, `ag_dashboard/`, `harness_kit/` | 147 / 29,787 | 15 / 1,339 |

Method: enumerate `git ls-files`, filter `.py`/`.ts`, and count
`len(path.read_bytes().splitlines())`. Lines include blanks and comments.
For reproduction after publishing the tour, enumerate the pinned upstream
revision with `git ls-tree -r --name-only <revision>` and read that revision's
blobs, rather than counting the fork's new files. HTML/CSS/JavaScript assets
also exist; this table does not purport to count every language or report
GitHub Linguist percentages.

## Claims that should not be mistaken for results from this exploration

Upstream's checked-in
[results page](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/docs/index.html#L147-L183)
describes benchmark gains. These are **upstream claims, not independently
reproduced measurements here**.

- **Coding:** a variation of SWE-bench removes part of a task specification
  and plants it into a history containing other tasks. This measures recovery
  of intentionally missing historical context, not an ordinary unmodified
  SWE-bench leaderboard run.
- **Data analysis:** a BirdInteract-derived setup plants choices about tables
  and columns in history. Its difficulty deliberately includes remembering
  those choices.
- **Session analysis:** questions about Spider 2.0-derived histories are
  scored with set F1. F1 and task accuracy are different metrics.
- **Parallel/environment settings:** the page compares AG-Codex against
  Codex and a trace-location hint baseline. Its scenarios target awareness
  across sessions and awareness of changed files.

The headline says “+32%” and “+31%.” The
[figure descriptions](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/docs/index.html#L117-L125)
give **91% versus 59%** and **100% versus 69%**. Those differences are **32
and 31 percentage points**, not 32% and 31% relative improvements. The detailed
single-agent caption separately reports +27 points coding, +36 points data
analysis, and +0.19 F1 session analysis. Preserve the task/metric distinction
when citing these figures.

The inspected checkout contains demos, recorded harness fixtures, and a large
automated suite. This exploration did not identify and execute a complete
reproduction pipeline for all published benchmarks, reconstruct sample sizes
or uncertainty intervals, or validate cost/latency methodology. That is a
bounded statement about this inspection, not proof that no evaluation assets
exist elsewhere. The tour's deterministic tests do not validate LLM accuracy.

## Implementation limitations that matter in practice

| Area | Source-grounded boundary | Practical consequence/inference |
| --- | --- | --- |
| Sharing | `parallel_requests` shares user requests; selected task text can be included by builds. | Do not expect every assistant answer to broadcast immediately. Related sessions need a compatible trust/instruction scope. |
| Semantic analysis | Segmentation, retention, cleaned requests, and ranking depend on model output. | Structural parsing does not establish summary fidelity or correct task boundaries. |
| Context maximum | `stubbed` keeps user messages; `read_within` can log and return above the maximum. | Treat the limit as an attempted budget, not unconditional admission control. |
| File awareness | Named existing files, mtime polling, capped sets, own-tool-reference and own-write heuristics. | Missed or unnecessary warnings are possible; no filesystem locking or atomic world snapshot. |
| Latency | Reads can wait for builds; policy wait ceilings and client response timeouts differ. | Background analysis can still delay a model call or lose its replacement to a client timeout. |
| Recovery | Many failures return original harness context. | Successful agent output is not itself proof that the Gatherer participated. |
| Compaction | Pi and OpenCode disable native compaction under different conditions. | Test the specific harness path; fallback is not identical across integrations. |
| Storage | Local plaintext SQLite and logs; WAL with `synchronous=NORMAL`. | Protect the home directory, backups, and exported traces; do not assume encryption or zero-loss power-failure durability. |
| Dashboard | Process launching, shell/editor/configuration routes; loopback and Host/origin checks. | It is a privileged local control surface, not an authenticated multi-tenant service. |

Sources and details are in [Policy](policy.md),
[Walkthroughs](walkthroughs.md), and
[`ag_dashboard/server.py`](https://github.com/ucbepic/actor-gatherer/blob/26286542395552892e977b0249cd31330d004aa8/ag_dashboard/server.py#L479-L515).
These are engineering boundaries, not a claim that the framework is unsuitable
for every use. No penetration test, deployment review, sustained concurrency
load test, or real provider compatibility matrix was performed.

**Not run:** paid/live Actor or Gatherer sessions; the benchmark suite behind
the results figures; a dashboard browser walkthrough; macOS-specific watchers;
live Claude/Codex/Pi/OpenCode version combinations. The added artifacts do not
modify a runtime UI.

## Organizational fork verification and publication history

Destination: **[chimera-research/actor-gatherer](https://github.com/chimera-research/actor-gatherer)**.
The initial accessible organization listing contained no matching fork, and
the destination lookup returned 404. The authorized command
`gh repo fork ucbepic/actor-gatherer --org chimera-research --clone=false`
returned **HTTP 403: “Resource not accessible by integration.”** Work was
preserved locally as a patch and source snapshot; no alternate fork was made.

The owner subsequently created the organizational fork and explicitly
authorized resuming publication. GitHub's repository API then confirmed
`fork=true`, both `parent.full_name` and `source.full_name` equal to
`ucbepic/actor-gatherer`, and write permission for the integration.

The fork's default branch was `main`, at
[`d6d9f6d2a698017e87c12923fcb4be847488f467`](https://github.com/ucbepic/actor-gatherer/commit/d6d9f6d2a698017e87c12923fcb4be847488f467),
identical to the fetched upstream `main`. Four other existing branches were
left untouched. No `exploration/` files existed at that base, and its README,
license, package metadata, Python source, and TypeScript source were unchanged
from the inspected revision.

The two intervening commits were upstream PR #180 and its merge. Their diff
changed only `ag_dashboard/page.html` and `ag_dashboard/TODO.md`, extending
Escape-key interruption in Chat. The tour was carried forward onto this newer
base, preserving both files exactly. Its source references, language inventory,
and original test record remain tied to the inspected revision rather than
being silently relabeled as a new audit.

Validation repeated on the publication base with the tour present:

- `python3 -B -S exploration/offline_lab.py`: all six demonstrations passed,
  with zero LLM calls.
- `python -m unittest discover -s tests -q`, using the same virtual environment
  and `ulimit -n 8192`: **1,286 tests, OK**, 132.717 seconds. The existing
  unclosed-socket `ResourceWarning` remained.
- `node --test --experimental-strip-types --no-warnings tests/ts/*.test.ts`:
  **43 passed, 0 failed**.
- All **135** source/local guide links, line ranges, local anchors, and code
  fences passed validation; the three SQL examples returned expected results.
- The staged diff passed `git diff --cached --check` and contained only the
  root README note and the eight files under `exploration/`. Runtime source,
  tests, workflows, package metadata, upstream documentation/assets, and the
  MIT license were unchanged from the publication base.

Publication uses one documentation commit as a normal fast-forward update to
the fork's `main`, with no force push, branch deletion, runtime changes, or
upstream contribution. The existing release/site workflows do not deploy or
publish packages on a push to `main`; no release or manual workflow dispatch
is part of this work. This is repository publication, not a Pages deployment
or a PyPI release.
