#!/usr/bin/env python3
"""Announce the model at session start, and any model or effort change after that.

Runs as a Claude Code hook. Two facts make this less obvious than it sounds:

* **No hook carries the model.** Claude Code puts it in no payload and sets no
  environment variable for it. `/model` writes the choice to ~/.claude/settings.json, so
  that file is the source of truth and this reads it directly.
* **No hook fires on a model change.** There is no such event, so this compares against
  the last value it saw and reports the difference. `Stop` is the carrier: it fires once
  per turn and is one of the events that includes `effort`.

Nothing here may break a session: every failure path exits 0 and stays silent.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS = CLAUDE_DIR / "settings.json"
ACCOUNT = Path.home() / ".claude.json"
STATE = CLAUDE_DIR / ".clauden.json"
PLUGIN_NAME = "clauden"

TIMEOUT_SECONDS = 4

# Effort is absent from SessionStart — it only appears in tool-use context. This marks
# "not reported" so it is never mistaken for a real value and never announced as a
# change, which would otherwise fire on the first turn of every session.
UNKNOWN = "unknown"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def current_model() -> str:
    """The model `/model` last selected.

    An absent key means the user never chose one and is on the account default, which is
    a real state worth reporting rather than an error.
    """
    return str(read_json(SETTINGS).get("model") or "default")


def current_effort(hook: dict) -> str:
    level = (hook.get("effort") or {}).get("level")
    return str(level or os.environ.get("CLAUDE_EFFORT") or UNKNOWN)


def device() -> str:
    try:
        return f"{os.environ.get('USER') or 'unknown'}@{socket.gethostname()}"
    except Exception:
        return "unknown"


def claude_account() -> str:
    """The Claude login this machine is authenticated as.

    Recorded by Claude Code in ~/.claude.json. Unlike the declared email it cannot be
    set to something else without actually logging in as someone else — but where a team
    shares one subscription it is identical for everybody, which is exactly why the
    declared email is asked for separately.
    """
    account = read_json(ACCOUNT).get("oauthAccount") or {}
    return str(account.get("emailAddress") or "").strip()


def declared_email() -> str:
    """The email entered at install. Required, so absence is worth shouting about."""
    return os.environ.get("CLAUDEN_EMAIL", "").strip() or "UNIDENTIFIED (email not set)"


def context_lines(cwd: str) -> list[str]:
    lines = [
        f"• account `{claude_account() or 'not logged in'}`",
        f"• device `{device()}`",
    ]
    if cwd:
        lines.append(f"• dir `{cwd}`")
    return lines


def installed_message(model: str, effort: str, cwd: str) -> list[str]:
    state = f"• model `{model}`"
    if effort != UNKNOWN:
        state += f" · effort `{effort}`"
    return [f"*{declared_email()}* installed clauden", state, *context_lines(cwd)]


def disabled_message(cwd: str) -> list[str]:
    return [
        f":warning: *{declared_email()}* disabled clauden — reporting stops here",
        *context_lines(cwd),
    ]


def still_enabled() -> bool:
    """Whether this plugin is still switched on in the user's settings.

    Best effort only. A disabled plugin's hooks do not run, so this can only catch the
    case where ConfigChange fires while the hook is still registered. Uninstalling
    removes the files outright and cannot be caught at all.
    """
    enabled = read_json(SETTINGS).get("enabledPlugins") or {}
    for key, value in enabled.items():
        if key.split("@", 1)[0] == PLUGIN_NAME:
            return bool(value)
    return True


def started_message(model: str, effort: str, cwd: str) -> list[str]:
    state = f"• model `{model}`"
    if effort != UNKNOWN:
        state += f" · effort `{effort}`"
    return [f"*{declared_email()}* started a session", state, *context_lines(cwd)]


def changed_message(
    changes: list[tuple[str, str, str]], model: str, effort: str, cwd: str
) -> list[str]:
    what = " and ".join(name for name, _, _ in changes)
    lines = [f"*{declared_email()}* changed {what}"]
    lines += [f"• {name} `{before}` → `{after}`" for name, before, after in changes]
    # Repeat whichever of the pair did not change, so a single message always carries the
    # full current state rather than only the delta.
    changed = {name for name, _, _ in changes}
    if "model" not in changed:
        lines.append(f"• model `{model}`")
    if "effort" not in changed and effort != UNKNOWN:
        lines.append(f"• effort `{effort}`")
    return lines + context_lines(cwd)


def detect_changes(
    previous: dict, model: str, effort: str
) -> list[tuple[str, str, str]]:
    """Differences worth reporting.

    A value only counts as changed if the previous one was actually observed. Learning a
    value for the first time — which happens on the first turn of every session, because
    SessionStart cannot see effort — is not a change the user made.
    """
    changes: list[tuple[str, str, str]] = []
    was_model = previous.get("model")
    if was_model and was_model != model:
        changes.append(("model", was_model, model))
    was_effort = previous.get("effort")
    if (
        was_effort
        and was_effort != UNKNOWN
        and effort != UNKNOWN
        and was_effort != effort
    ):
        changes.append(("effort", was_effort, effort))
    return changes


def post(webhook: str, lines: list[str]) -> None:
    body = json.dumps({"text": "\n".join(lines)}).encode("utf-8")
    request = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        # A webhook that is down must not stall or fail the user's session.
        pass


def main() -> int:
    webhook = os.environ.get("CLAUDEN_WEBHOOK", "").strip()
    if not webhook:
        return 0

    hook = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            hook = json.loads(raw)
    except Exception:
        pass

    model, effort = current_model(), current_effort(hook)
    previous = read_json(STATE)
    cwd = hook.get("cwd", "")

    event = hook.get("hook_event_name")

    if event == "ConfigChange":
        # Only worth a message if it is *this* plugin being switched off.
        if not still_enabled():
            post(webhook, disabled_message(cwd))
        return 0

    if not previous:
        # No state file means this machine has never run clauden: a first install.
        post(webhook, installed_message(model, effort, cwd))
    elif event == "SessionStart":
        # Always announce a new session, so the channel shows what each one runs on
        # rather than only what changed.
        post(webhook, started_message(model, effort, cwd))
    else:
        # A first run has nothing to compare against. Recording the baseline silently
        # avoids telling everyone that everyone "switched" the moment this is installed.
        changes = detect_changes(previous, model, effort) if previous else []
        if changes:
            post(webhook, changed_message(changes, model, effort, cwd))

    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite a known effort with UNKNOWN from an event that omits it.
        STATE.write_text(
            json.dumps(
                {
                    "model": model,
                    "effort": effort
                    if effort != UNKNOWN
                    else previous.get("effort", UNKNOWN),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never fail a session because a notifier had a bad day.
        sys.exit(0)
