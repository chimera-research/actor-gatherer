#!/usr/bin/env python3
"""Exercise real storage/policy mechanics with no model, credentials, or network.

Run from a source checkout: python3 -S exploration/offline_lab.py
Python 3.11+; standard library only. -S excludes installed site packages.
All data lives in a temporary directory, removed on exit. Assertions are
intentional learning checks; do not run with Python's -O option.
"""

import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="ag-offline-lab-") as tmp:
        # paths.py reads AG_HOME at import time. Never use the reader's real home.
        os.environ["AG_HOME"] = str(Path(tmp) / "ag-home")
        from ag.ag_harness import Manager
        from ag.ag_harness.store import schema
        from ag.ag_interface import Event, FORMAT, LLM, Tokenizer
        from ag.ag_policies.proactive_context_manager import (
            ProactiveContextManager,
            ProactiveContextManagerConfig,
        )
        from ag.ag_pollers.file_changes import FileChangePoller

        class CharacterCounter(Tokenizer):
            """One character = one lab unit, NOT a provider token estimate."""

            def count(self, text):
                return len(text)

        class NoModel(LLM):
            """A tripwire: this exercise must never ask an LLM anything."""

            calls = 0

            def complete(self, prompt, **kwargs):
                self.calls += 1
                raise AssertionError("The offline lab unexpectedly called an LLM")

        llm = NoModel()
        tok = CharacterCounter()
        policy = ProactiveContextManager(
            FORMAT, llm, ProactiveContextManagerConfig(gatherer_guide=""),
            tokenizer=tok, jobs=None,
        )
        manager = Manager(policy, tokenizer=tok)

        def put(gatherer, channel, kind, event_id, text, **properties):
            types = {t.name: t.id for t in manager.event_types(gatherer)}
            return manager.insert(gatherer, Event(
                types[kind], {"text": text}, id=event_id, text=text,
                properties={"channel": channel, **properties},
            ))

        try:
            manager.init("identity")
            first = put("identity", "A", "user_message", "same", "Original", cwd=tmp)
            again = put("identity", "A", "user_message", "same", "Changed", cwd="/elsewhere")
            other = put("identity", "B", "user_message", "same", "Other channel")
            anonymous = [put("identity", "A", "user_message", None, "No ID") for _ in range(2)]
            identity = manager.store("identity")
            rows = identity.rows(match={"channel": "A"})
            assert first is not None and again is None and other != first
            assert identity.execute("SELECT count(*) FROM events").fetchone()[0] == 4
            assert len(rows) == 3 and rows[0].payload == {"text": "Original"}
            assert identity.rows(match={"channel": "B"})[0].payload == {"text": "Other channel"}
            assert rows[0].properties["cwd"] == tmp and anonymous[0] != anonymous[1]
            print("[ok] Identity: first insert wins; channel distinguishes; no ID means new")

            manager.init("team")
            put("team", "B", "user_message", "b1", "Use CAD for this report.")
            foreign_answer = put("team", "B", "agent_message", "b2", "B-only calculation: 731.")
            question = put("team", "A", "user_message", "a1", "What is the total?")
            context, read_id, _ = manager.read_logged("team", question, properties={"channel": "A"})
            shared = next(i for i, e in enumerate(context) if e.get("name") == "parallel_request")
            own = next(i for i, e in enumerate(context) if e.get("id") == "a1")
            assert shared < own and "Use CAD" in context[shared]["text"]
            assert [e["id"] for e in context if e["type"] != "ag"] == ["a1"]
            assert "B-only calculation" not in str(context)
            print("[ok] Sharing: B's request becomes text before A's request; B's raw answer stays out")

            store = manager.store("team")
            logged = store.last_read({"channel": "A"})
            assert logged["read_id"] == read_id and len(logged["refs"]) == len(context)
            assert logged["refs"][shared].made_id is not None
            assert logged["refs"][own].row_id == question
            assert all(ref.row_id != foreign_answer for ref in logged["refs"])
            put("team", "B", "user_message", "b3", "Exclude refunds from the total.")
            before = list(store.iterdump())
            preview, _ = manager.context_only("team", question, properties={"channel": "A"})
            assert "Exclude refunds" in str(preview)
            assert list(store.iterdump()) == before
            print("[ok] Provenance: raw/made references logged; context_only leaves database unchanged")

            root = Path(tmp) / "files"
            root.mkdir()
            for name in ("prices.csv", "unmentioned.csv"):
                path = root / name
                path.write_text("old value\n")
                os.utime(path, (time.time() - 10, time.time() - 10))
            manager.set_pollers([FileChangePoller(str(root))])
            manager.init("files")
            put("files", "A", "user_message", "f1", "Read prices.csv", cwd=str(root))
            put("files", "A", "tool_call", "f2", "cat prices.csv", cwd=str(root))
            output = put("files", "A", "tool_output", "f3", "old value", cwd=str(root))
            initial = manager.read_events("files", output, properties={"channel": "A", "cwd": str(root)})
            assert not any(e.get("name") == "environment_update" for e in initial)
            for name in ("prices.csv", "unmentioned.csv"):
                path = root / name
                path.write_text("NEW CONTENT IS NOT IN THE NOTICE\n")
                now = time.time()
                os.utime(path, (now, now))
            followup = put("files", "A", "user_message", "f4", "Compute the total", cwd=str(root))
            changed = manager.read_events("files", followup, properties={"channel": "A", "cwd": str(root)})
            notices = [e["text"] for e in changed if e.get("name") == "environment_update"]
            updates = [r for r in manager.store("files").rows() if r.type.name == "environment_update"]
            assert len(notices) == 1 and "prices.csv" in notices[0]
            assert "read the file again" in notices[0] and "NEW CONTENT" not in notices[0]
            assert [r.payload["subject"] for r in updates] == ["prices.csv"]
            print("[ok] Polling: real named-file edit produces a notice, not contents; unnamed edit ignored")
            manager.set_pollers([])

            manager.init("separate")
            isolated = put("separate", "A", "user_message", "a1", "What is the total?")
            separate = manager.read_events("separate", isolated, properties={"channel": "A"})
            assert not any(e["type"] == "ag" for e in separate)
            assert "Use CAD" not in str(separate) and "Exclude refunds" not in str(separate)
            print("[ok] Isolation: same channel/ID in another gatherer does not share team context")

            # Deliberately make user input alone exceed the whole budget. There
            # are no agent steps to stub. Disabling jobs isolates the final
            # assembly fallback; this does NOT test semantic condensation.
            tiny = ProactiveContextManagerConfig(
                min_context_tokens=0, max_context_tokens=100, gatherer_guide="",
                all_task_tokens=0, parallel_index_tokens=0, keep_pinned_tokens=0,
                keep_previous_task_tokens=0, keep_temporal_relevant_tokens=0,
                keep_task_relevant_tokens=0, keep_so_far_tokens=0,
            )
            logs = []
            limited = Manager(ProactiveContextManager(FORMAT, llm, tiny, tokenizer=tok, jobs=None, log=logs.append))
            limited.init("limit")
            user_type = next(t.id for t in limited.event_types("limit") if t.name == "user_message")
            text = "x" * 200
            row = limited.insert("limit", Event(user_type, {"text": text}, text=text, properties={"channel": "A"}))
            oversized, _, sizes = limited.read_logged("limit", row, properties={"channel": "A"})
            assert oversized[0]["payload"]["text"] == text
            assert sizes["tokens"] == 200 and sizes["budget"] == 100
            assert any("over max_context_tokens=100" in line for line in logs)
            assert llm.calls == 0
            print("[ok] Budget boundary: 200 lab units returned for a 100-unit budget; user text preserved")
            print("PASS: 6 demonstrations; 0 LLM calls. Temporary databases will be removed.")
        finally:
            # Cached connections must close before temporary databases disappear.
            schema.release()


if __name__ == "__main__":
    main()
