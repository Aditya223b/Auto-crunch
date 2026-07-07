# Auto-crunch Product Plan

## Goal

Auto-crunch supervises AI coding CLIs such as Claude Code and Codex. It watches permission prompts and clarification questions, decides what can be approved automatically, and routes real user decisions to WhatsApp.

Auto-crunch must not delegate product or planning decisions to the underlying CLI. A permission prompt is different from an owner decision.

## Runtime Recommendation

Use a visible terminal wrapper plus a small background service.

- The wrapper runs the AI CLI in a PTY and can approve prompts or type answers.
- The background service receives Meta WhatsApp Cloud API webhooks, stores pending questions, and generates summaries.

This is better than a fully hidden daemon for the first release because users can see what the underlying CLI is doing, and debugging terminal behavior is much easier.

## MVP Stack

- Python
- `pexpect` for PTY control
- `typer` or `argparse` for CLI
- SQLite for audit logs and pending decisions
- FastAPI for the local webhook service
- Meta WhatsApp Cloud API
- macOS `launchd`

## v0.1 Features

- `autocrunch start claude`
- `autocrunch start codex`
- Claude Code adapter
- Codex adapter
- Rule-based severity classifier
- Configurable auto-approve ceiling: `low`, `medium`, or `high`
- Critical actions require explicit human approval
- Owner-decision classifier for PRDs, implementation plans, tech-stack choices, architecture choices, and clarification questions
- Meta WhatsApp Cloud API clarification routing
- Meta WhatsApp Cloud API approval routing when policy requires it
- SQLite audit log
- Weekly markdown summaries

## Prompt Categories

Permission prompts:

- Run a terminal command
- Read, edit, create, or delete a file
- Access network
- Push or pull from Git
- Start a local server
- Install dependencies

These can be classified by severity and auto-approved up to the user's configured ceiling.

Owner decisions:

- Draft or approve a PRD
- Draft or approve an implementation plan
- Choose a tech stack
- Choose architecture
- Decide scope or product behavior
- Answer a clarification question
- Confirm "should I proceed with implementation?"

These are not permissions. Auto-crunch should route them to the owner and inject the answer back into the CLI. The underlying tool should not continue from planning into implementation unless the owner says so.

## Severity Model

Low:

- Read/edit/create files inside the current project
- Run tests, linters, formatters
- Inspect Git state with `git status`, `git diff`, `git log`

Medium:

- Install declared dependencies
- `git pull`
- Read-only network requests
- File access in user-approved folders
- Routine local build commands

High:

- `git push`
- Access outside the project folder
- Delete files inside project scope
- Install undeclared packages
- Run downloaded binaries
- Create background jobs, launch agents, or shell profile changes
- Non-destructive GitHub operations that publish code or comments under the user's identity

Critical:

- Exfiltrate secrets or private files
- Access SSH keys, browser profiles, keychains, or cloud credentials
- Destructive system commands
- Force-push protected branches
- Disable security tools
- Modify Auto-crunch policy to reduce oversight

Critical is intentionally outside the auto-approve ceiling.
