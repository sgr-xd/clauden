"""End-to-end tests for watch.py: the real script, real hook payloads, a real local webhook.

    python3 -m unittest discover -s tests

Each test runs watch.py as Claude Code would — a subprocess fed a hook payload on stdin —
with HOME pointed at a temporary directory, so settings.json and the state file are the
test's own. The webhook is an HTTP server on localhost that records every POST.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WATCH = Path(__file__).resolve().parent.parent / "watch.py"
OPUS, SONNET = "claude-opus-5", "claude-sonnet-5"


class Webhook(ThreadingHTTPServer):
    def __init__(self) -> None:
        self.posts: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.posts.append(json.loads(body)["text"])
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        super().__init__(("127.0.0.1", 0), Handler)


class WatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        (self.home / ".claude").mkdir()
        self.webhook = Webhook()
        threading.Thread(target=self.webhook.serve_forever, daemon=True).start()
        self.addCleanup(self.webhook.shutdown)
        # An existing install: the first-ever run announces the install, which is not
        # what these tests are about.
        self.write(".claude/.clauden.json", {"model": SONNET, "effort": "high", "session": "earlier"})

    def write(self, name: str, data: dict) -> None:
        (self.home / name).write_text(json.dumps(data), encoding="utf-8")

    def use_model(self, model: str) -> None:
        self.write(".claude/settings.json", {"model": model})

    def hook(self, event: str, session: str, effort: str | None = "high") -> None:
        payload = {"hook_event_name": event, "session_id": session, "cwd": "/work/demo"}
        if effort and event != "SessionStart":  # SessionStart carries no effort
            payload["effort"] = {"level": effort}
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CLAUDEN"))}
        env.update(
            HOME=str(self.home),
            CLAUDEN_WEBHOOK=f"http://127.0.0.1:{self.webhook.server_address[1]}/",
            CLAUDEN_EMAIL="dev@example.com",
        )
        subprocess.run([sys.executable, str(WATCH)], input=json.dumps(payload), text=True, env=env, check=True)

    def test_session_starting_on_opus_is_reported_on_its_first_turn(self) -> None:
        # Regression: SessionStart recorded the new session id, so the first Stop took it
        # for an old session and never said the session was working on Opus.
        self.use_model(OPUS)
        self.hook("SessionStart", "s1")
        self.assertEqual(self.webhook.posts, [], "opening a session must stay silent")
        self.hook("Stop", "s1")
        self.assertEqual(len(self.webhook.posts), 1)
        self.assertIn(f"is working on `{OPUS}`", self.webhook.posts[0])
        self.hook("Stop", "s1")
        self.assertEqual(len(self.webhook.posts), 1, "later turns must not re-announce")

    def test_session_on_the_quiet_model_says_nothing(self) -> None:
        self.use_model(SONNET)
        self.hook("SessionStart", "s1")
        self.hook("Stop", "s1")
        self.hook("Stop", "s1")
        self.assertEqual(self.webhook.posts, [])

    def test_switching_to_opus_is_reported_and_back_to_sonnet_is_not(self) -> None:
        self.use_model(SONNET)
        self.hook("SessionStart", "s1")
        self.hook("Stop", "s1")
        self.use_model(OPUS)
        self.hook("Stop", "s1")
        self.assertEqual(len(self.webhook.posts), 1)
        self.assertIn(f"`{SONNET}` → `{OPUS}`", self.webhook.posts[0])
        self.use_model(SONNET)
        self.hook("Stop", "s1")
        self.assertEqual(len(self.webhook.posts), 1)


if __name__ == "__main__":
    unittest.main()
