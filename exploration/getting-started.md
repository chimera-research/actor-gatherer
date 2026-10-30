# Getting started: learn offline before paying for model calls

[Tour home](README.md) · Previous: [Walkthroughs](walkthroughs.md) · Next: [Evidence](evidence.md)

## First, run six mechanics without installing dependencies

Clone the learning fork if you do not already have it:

```bash
git clone https://github.com/chimera-research/actor-gatherer.git
cd actor-gatherer
```

From the root of that checkout, with Python 3.11+:

```bash
python3 -S exploration/offline_lab.py
```

`-S` excludes installed site packages. The lab imports the real repository
source, uses SQLite from the standard library, supplies a deliberately simple
character counter, and disables background jobs. Its model client is a
tripwire that fails if called. It sets a temporary `AG_HOME` **before** the
storage imports, closes cached connections, and removes its data on exit.
It does not use your real `~/.ag`, credentials, or a running coding harness.
Do not pass `-O`: the exercises use assertions.

The output ends with:

```text
PASS: 6 demonstrations; 0 LLM calls. Temporary databases will be removed.
```

| Demonstration | What to look for in the script |
| --- | --- |
| Identity | A repeated ID in A is ignored despite changed text/cwd; the same ID in B is separate; absent IDs are new rows. |
| Sharing | B's user request becomes an `ag` text message before A's request; B's raw answer is not included. |
| Provenance/preview | Ordered read references name raw or made items; `Manager.context_only` can assemble a new note without changing the original database. |
| Environment | A real edit to a tool-mentioned file produces a re-read notice; an unmentioned edit produces no update. |
| Scope | Another gatherer with the same channel/ID receives none of the first gatherer's context. |
| Budget edge | A 200-character user message survives a 100-unit maximum; the policy logs the remaining excess. |

These are real store/poller/policy executions, **not live LLM demonstrations**.
They do not test semantic task splitting, summary fidelity, provider token
counts, or whether an Actor obeys the resulting context. The lab's token unit
is a character, not a model token. Disabling jobs intentionally isolates
assembly from semantic condensation.

## Install the full project in an isolated environment

Use the checkout's source, not an unpinned PyPI version, to match this tour:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
ag --help
```

Alternatively, `uv venv .venv` followed by `uv pip install --python
.venv/bin/python -e .` installs the same base project. The upstream
`requirements.txt` requests `.[codex]`, including the optional Codex SDK.
Use `python -m pip install -e '.[codex]'` if the **Gatherer's own model client**
will use Codex. An Actor harness binary, its login, and its prerequisites are
separate from installing this Python package.

The learning fork contains this tour; the upstream repository and PyPI release
need not. Source explanations remain pinned to the inspected revision named in
[the index](README.md), which also records the newer publication base and its
limited dashboard-only drift.

## An optional live experiment, deliberately separated from offline validation

The following is a learning recipe, **not a run performed in this exploration**.
It makes model calls and may incur charges. Use a disposable working directory
and non-sensitive content. An Actor can run tools and write files there.

1. Set a new home in every terminal used for the experiment. For example:

   ```bash
   export AG_HOME="$HOME/.ag-learning-tour"
   ```

   Choose another unused directory if that one already holds work. This
   isolates configuration/history, not the Actor's filesystem permissions.

2. Configure the Gatherer's model. For an already authenticated Claude Code
   installation, upstream supports `ag model claude-code/sonnet`. An API model
   uses `ag model provider/model` and credentials in the provider's normal
   environment variables. Use a supported model available to your account;
   check the [upstream model reference](../docs/docs.md). Do not put a key in
   tracked configuration or in this tour. `ag model` shows the current choice.

3. Preview a launch without running the harness:

   ```bash
   ag --dry-run --gatherer learning codex exec "Let X = 5. What is 2X?"
   ```

   A dry run checks/resolves setup; it is not proof of successful model
   authentication or of an eventual context rewrite. For live runs, use a
   harness already installed and logged in. The CLI chooses the Actor; the
   preceding model setting chooses the Gatherer's analysis model.

4. In a disposable working directory, run two sessions in the same scope:

   ```bash
   ag --gatherer learning codex exec "Let X = 5. What is 2X?"
   ag --gatherer learning claude "What is 3X?"
   ```

   With successful rewriting, the second session should receive the first
   user's request as Gatherer context. Whether the model uses it correctly
   is something to observe, not a scripted assertion of the answer.
   Repeat the second command with a **new, differently named gatherer** as
   a negative control. Reusing an old gatherer can contaminate the experiment.

5. Inspect `ag gatherers`, the gatherer's `context.db`, and its server/worker
   logs. On your own workstation, `ag dashboard --no-open` starts the local
   dashboard. In an Amp orb, use its supervised-service/portal mechanism
   instead of an unmanaged server; this exploration did not start one.
   Do not expose the dashboard to untrusted clients: it controls processes
   and files, and origin checks are not authentication.

The [upstream examples](../README.md#examples) also include salary-file edits
and a cross-session schema-join choice. Their printed answers are example
outcomes, not guarantees for arbitrary models or harness releases.

## Inspect a returned context rather than only the final answer

After your own live run, the default data path is
`$AG_HOME/gatherers/learning/context.db`. With the optional `sqlite3` CLI,
open it **read-only**:

```bash
sqlite3 -readonly "$AG_HOME/gatherers/learning/context.db"
```

These queries work against the pinned schema:

```sql
SELECT row_id, event_id, p_channel, t.name AS type, substr(text, 1, 100)
FROM events JOIN event_types t ON events.event_type_id = t.event_type_id
ORDER BY row_id;

SELECT read_id, p_channel, row_id, basis, est_tokens, sent_tokens, real_tokens
FROM _reads ORDER BY read_id;

SELECT position, row_id, made_id
FROM _read_items
WHERE read_id = (SELECT max(read_id) FROM _reads)
ORDER BY position;
```

An `events` row is an observation; a `_made_items` row is generated context.
`basis` refers to a policy analysis, not the latest user event. `real_tokens`
can be absent. A context note in the database proves construction; a recorded
read proves selection; neither alone proves that a remote model obeyed it.
Treat database and log contents as sensitive conversation history.

## Reproduce the existing automated checks

After the full base install, run the Python suite from the repository root:

```bash
ulimit -n 8192
python -m unittest discover -s tests -q
```

The raised limit is a workaround for retained test-fixture connections at this
revision, not a production tuning recommendation. If your hard limit prevents
raising it, run selected test modules in separate processes or address fixture
cleanup before expecting the whole suite to finish. Details and the original
failure are recorded in [Evidence](evidence.md).

For the TypeScript checks, use a Node release supporting type stripping
(validated here with Node 26.12.1):

```bash
node --test --experimental-strip-types --no-warnings tests/ts/*.test.ts
```

For focused study, `python -m unittest discover -s tests -p test_store.py -q`
exercises persistence; substitute `test_core.py` for policy orchestration or
`test_outside_events.py` for outside notices. These existing tests use fixtures,
scripted clients, and local servers; they do not establish benchmark accuracy.

## Troubleshooting by layer

| Symptom | First question to answer |
| --- | --- |
| No sharing | Do both sessions actually use the same gatherer and home? Is the other item a user request or only an assistant answer? |
| A rewrite appears ineffective | Does the hook's diagnostic say “messages unchanged”? Did the server log a successful read? |
| No long-history sections | Was a build due, completed, and adopted? A ready build alone is insufficient. |
| No file warning | Was the file existing, named by a prior own tool call, in retained raw context, and in the same cwd? Did the heuristic classify the change as an own write? |
| Token counts differ | Are you comparing policy-arranged tokens, all sent tokens, or provider-reported tokens? |
| Wrong history on resume | Did the resumed command name its original gatherer rather than falling back to `default`? |
| Provider rejection after a harness upgrade | Inspect the adaptor/fixture version and reconstructed request, not just the policy's selected rows. |

Do not delete an existing gatherer's database as a first debugging step. Start
a fresh named gatherer for comparisons and preserve the original evidence.
