# Clauden

A Claude Code plugin that posts to a webhook when a session starts, and whenever
someone changes their **model** or **reasoning effort**. That is all it does. No session
tracking, no prompt capture, no server to run.

```
*alice@macbook* started a session — model `claude-opus-5`, effort `high`
_in /work/proj_

*alice@macbook* changed Claude Code settings
• model: `claude-sonnet-5` → `claude-opus-5`
_in /work/proj_
```

## Install

```
/plugin marketplace add sgr-xd/clauden
/plugin install clauden
```

It asks for two things:

| Field | |
|---|---|
| **Webhook URL** | A Slack incoming webhook, or anything accepting `POST {"text": "..."}` |
| **Name to report** | Optional. Defaults to `user@hostname` |

Nothing is sent if the webhook is empty.

## How it works

Two facts make this less obvious than it looks:

**No hook carries the model.** Claude Code puts it in no payload and sets no environment
variable. `/model` writes the choice to `~/.claude/settings.json`, so that file is the
source of truth and the script reads it directly.

**No hook fires when the model changes.** There is no such event. So the script records
what it last saw in `~/.claude/.clauden.json` and reports the difference. `Stop` is
the carrier: it fires once per turn and is one of the events that includes `effort`.

`SessionStart` always announces the model. Changes are reported after that, on
`Stop`.

Effort is absent from `SessionStart` — Claude Code only includes it in tool-use context —
so it is omitted from the start message rather than guessed, and learning it on the first
turn is never reported as a change. Without that rule every session would open with a
false "effort changed" alert.

The first run records a baseline **silently** — otherwise installing this would announce
that everyone had just "switched".

## What it does not do

- Does not read prompts, responses, files or tool calls
- Does not send anything anywhere except the webhook you configure
- Does not run a server, or store anything beyond two strings in one local file
- **Does not enforce anything.** A plugin is installed and removable by the person using
  it. If you need model choice to be tamper-resistant rather than observable, that is
  managed settings pushed by MDM, not a plugin.

## Requirements

`python3`, which is present by default on macOS and Linux. No packages are installed and
the script imports only the standard library.

Every failure path exits 0 and stays quiet: no webhook configured, an unreachable
endpoint, malformed input, a missing settings file. A notifier must never break the
session it is watching.

## License

Apache-2.0
