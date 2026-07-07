# Auto-crunch

Auto-crunch is a macOS-first terminal supervisor for AI coding CLIs. The goal is to reduce routine permission interruptions, classify requested actions by severity, route real clarification questions to WhatsApp, and keep an audit trail.

Current implementation: a Claude Code launcher, policy config, and weekly summaries.

Planned v0.1 supervisor support:

- Claude Code
- Codex
- Meta WhatsApp Cloud API for clarification and approval messages

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Aditya223b/Auto-crunch/main/install.sh | bash
```

Restart your terminal, or run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Usage

Start Claude Code in the current project:

```bash
autocrunch run
```

Pass arguments through to Claude Code:

```bash
autocrunch run -- --model sonnet
```

Write a report manually:

```bash
autocrunch summary
```

Install the Monday 9:00 AM macOS weekly report job:

```bash
autocrunch install-scheduler
```

Check setup:

```bash
autocrunch doctor
```

Create or view policy config:

```bash
autocrunch policy init
autocrunch policy show
autocrunch policy explain
```

Choose how far Auto-crunch may auto-approve:

```bash
autocrunch policy set --auto-approve-until low
autocrunch policy set --auto-approve-until medium
autocrunch policy set --auto-approve-until high
```

## What Gets Logged

Auto-crunch logs launches to:

```text
~/.local/share/autocrunch/launches.jsonl
```

Weekly reports are written to:

```text
~/.local/share/autocrunch/reports/
```

Reports intentionally avoid full prompts, full command bodies, and file contents. They summarize launches, recent Claude session counts, tool usage, and command heads.

## Permission Modes

The current launcher uses Claude Code's native permission mode:

```bash
autocrunch run
```

This uses:

```text
claude --permission-mode auto --add-dir "$PWD"
```

The fuller supervisor will use Auto-crunch's own severity policy before approving prompts from Claude Code or Codex.

## Severity Policy

Each user chooses the highest severity level Auto-crunch may approve automatically:

```json
{
  "policy": {
    "auto_approve_until": "medium",
    "critical_requires_human": true
  }
}
```

Default: `medium`.

Allowed values:

- `low`: only simple project-local reads, edits, tests, and harmless inspection.
- `medium`: low plus routine installs, dependency pulls, network reads, file access in approved folders, and `git pull`.
- `high`: medium plus actions like `git push`, broader file access, deletes inside project scope, and non-trivial shell commands after severity analysis.

`critical` actions are not auto-approved by default. Examples: secret exfiltration, destructive system commands, credential access, `sudo` with destructive commands, disabling security tools, force-pushing protected branches, and modifying Auto-crunch policy to reduce oversight.

Advanced risky mode:

```bash
autocrunch run --mode bypassPermissions --i-understand-risk
```

This bypasses Claude Code permission checks. Use it only in a sandbox or throwaway dev environment.

## Target WhatsApp Flow

For a clarification question:

```text
Codex asks: "Should I use PostgreSQL or SQLite?"
```

Auto-crunch sends that to WhatsApp through Meta Cloud API, waits for the user's reply, then injects the answer back into the terminal session.

For a high-severity permission:

```text
Claude wants to run: git push origin main
Severity: high
Reply ALLOW or DENY.
```

If the user's policy is `auto_approve_until = "high"`, Auto-crunch may approve it automatically after analysis. If the policy is `medium`, it asks.

## macOS Status

This first version supports macOS. Linux and Windows support are planned after the macOS flow is stable.
