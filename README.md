# Clauden

A Claude Code plugin that posts to a webhook when a session starts and when someone
changes their **model** or **reasoning effort**. That is all it does — no prompt capture,
no session tracking, no server to run.

```
*alice@company.com* started a session
• model `claude-opus-5` · effort `high`
• account `team@company.com`
• device `alice@macbook`
• dir `/Users/alice/work/api`

*alice@company.com* changed model
• model `claude-sonnet-5` → `claude-opus-5`
• effort `high`
• account `team@company.com`
• device `alice@macbook`
• dir `/Users/alice/work/api`
```

## Setup

### Step 1 — add the marketplace

```
/plugin marketplace add sgr-xd/clauden
```

Expect: `Successfully added marketplace: clauden`

### Step 2 — install

```
/plugin install clauden@clauden
```

Expect: `Successfully installed` followed by `2 userConfig options not yet set`. That
warning is expected — step 3 sets them.

### Step 3 — configure

```
/plugin configure clauden@clauden
```

Fill in both fields. Neither can be left empty:

| Field | Example |
|---|---|
| **Your work email** | `alice@company.com` |
| **Webhook URL** | `https://hooks.slack.com/services/T…/B…/…` |

In the dialog: use `↑` `↓` to move between rows, type directly into the highlighted row,
then select **Save configuration** and press Enter. Pressing `Esc` discards everything.

> If the dialog looks garbled or repeats rows, your terminal is too short. Make the window
> taller (40+ rows) and reopen it.

Expect: `Configuration saved.`

### Step 4 — reload

```
/reload-plugins
```

Hooks register at session start, so a plugin installed mid-session does nothing until you
reload or start a new session.

### Step 5 — confirm it works

Send any message. When the turn ends you should see this in your channel:

```
*alice@company.com* installed clauden
• model `claude-opus-5` · effort `high`
• account `team@company.com`
• device `alice@macbook`
• dir `/Users/alice/work/api`
```

If it arrives, setup is done. To see a change notification, run `/model`, pick a different
model, and send another message.

### Getting a Slack webhook

[api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → *From scratch* →
name it and pick your workspace → **Incoming Webhooks** → toggle **On** → **Add New Webhook
to Workspace** → choose a channel. Copy the URL it gives you; that is what goes in step 3.

## Troubleshooting

**No message after step 5.** Check in this order:

1. `/plugin` → is clauden listed as **enabled**?
2. Did you `/reload-plugins` after configuring? Hooks are registered at session start.
3. Is `~/.claude/.clauden.json` present? If it exists, the hook has run — so the problem is
   the webhook, not the plugin. If it is absent, the hook has not run.
4. Test the webhook directly:
   ```bash
   curl -X POST -H 'Content-Type: application/json' \
     --data '{"text":"test"}' '<your webhook url>'
   ```
   It should return `ok`.

**A notification fires but names the wrong person.** The email is whatever was typed at
install. Re-run `/plugin configure`.

**Nothing after switching model.** Changes are reported on the *next turn*, not when you
run `/model`. Send a message.

**Updating to a new version.** Use `/plugin` → **Update now**, which preserves your
configuration. Uninstalling and reinstalling erases it and you will have to configure again.

## What gets sent

Every message carries six fields. **Read this before installing** — one of them is your
working directory:

| Field | Where it comes from |
|---|---|
| Your email | what you typed at install |
| Claude account | `~/.claude.json` — the login this machine is authenticated as |
| Model | `~/.claude/settings.json`, written by `/model` |
| Effort | the hook payload, or `$CLAUDE_EFFORT` |
| Device | `$USER` and hostname |
| **Working directory** | the directory the session is running in |

The working directory is included because it says *where* someone is doing the work, which
is usually the useful part of a notification. It also means directory names — which often
carry project or client names — appear in whatever channel the webhook points at. Point it
somewhere that is fine with that.

## When messages are sent

| Event | Message |
|---|---|
| First run on a machine | `installed clauden` |
| Session start | `started a session` |
| Model or effort changed | `changed model` / `changed effort`, with `before → after` |
| Plugin disabled | ⚠️ `disabled clauden` — best effort, see below |

Changes are reported **once**, on the first turn after the change — not on every message.
Switching model and then sending nothing produces no notification until the next session
starts, which reports the current model anyway.

## How it works

Two facts about Claude Code make this less obvious than it looks.

**No hook carries the model.** It appears in no payload and there is no environment
variable for it. `/model` writes the choice to `~/.claude/settings.json`, so that file is
the source of truth and the script reads it directly.

**No hook fires when the model changes.** There is no such event. So the script records
what it last saw in `~/.claude/.clauden.json` — two strings — and reports the difference.
`Stop` is the carrier: it fires once per turn and is one of the events that also includes
`effort`.

Effort is absent from `SessionStart`, appearing only in tool-use context. It is therefore
omitted from the start message rather than guessed, and learning it for the first time is
never reported as a change. Without that rule every session would open with a false
"effort changed" alert.

Configuration is read from `CLAUDE_PLUGIN_OPTION_*`, which Claude Code exports to the hook.
Interpolating `${user_config.*}` into a hook command is refused — the substituted value
would be re-parsed by the shell — and reading the environment also keeps the values out of
the process command line.

## What it does not do

- Does not read prompts, responses, files, or tool calls
- Does not send anything anywhere except the webhook you configure
- Does not run a server; it stores two strings in one local file
- **Does not detect uninstalls.** A disabled plugin's hooks do not run and an uninstalled
  one has no files left, so a plugin cannot reliably report its own removal. The disable
  notice hooks `ConfigChange` and loses that race sometimes. Guaranteed detection needs
  absence-checking wherever the messages arrive.
- **Does not enforce anything.** A plugin is installed and removable by the person using
  it. If model choice needs to be tamper-resistant rather than merely observable, that is
  managed settings pushed by MDM — not a plugin.

## Where things are stored

| | |
|---|---|
| Your email and webhook URL | `~/.claude/settings.json` under `pluginConfigs`, in plain text so an administrator can confirm what was configured |
| Last seen model and effort | `~/.claude/.clauden.json` |

## Requirements

`python3`, present by default on macOS and Linux. Nothing is installed; the script imports
only the standard library.

Every failure path exits 0 and stays quiet — no webhook configured, an unreachable
endpoint, malformed input, a missing settings file. A notifier must never break the session
it is watching.

## License

Apache-2.0
