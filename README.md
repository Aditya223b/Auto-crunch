# Auto-crunch

Auto-crunch is a macOS-first terminal helper for Claude Code. It reduces routine permission interruptions while you build inside a project folder and writes a weekly activity summary for review.

It uses Claude Code's native permission modes. By default, Auto-crunch runs Claude Code with `--permission-mode auto`, scoped to the directory where you launch it.

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

Default:

```bash
autocrunch run
```

This uses:

```text
claude --permission-mode auto --add-dir "$PWD"
```

Advanced risky mode:

```bash
autocrunch run --mode bypassPermissions --i-understand-risk
```

This bypasses Claude Code permission checks. Use it only in a sandbox or throwaway dev environment.

## macOS Status

This first version supports macOS. Linux and Windows support are planned after the macOS flow is stable.

