#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


APP_NAME = "autocrunch"
LABEL = "io.github.aditya223b.autocrunch.weekly-summary"
DEFAULT_REPORT_HOUR = 9
DEFAULT_REPORT_MINUTE = 0
SEVERITY_ORDER = ["low", "medium", "high", "critical"]
DEFAULT_AUTO_APPROVE_UNTIL = "medium"


def home() -> Path:
    return Path.home()


def state_dir() -> Path:
    return Path(os.environ.get("AUTOCRUNCH_STATE_DIR", home() / ".local" / "share" / APP_NAME))


def config_dir() -> Path:
    return Path(os.environ.get("AUTOCRUNCH_CONFIG_DIR", home() / ".autocrunch"))


def config_path() -> Path:
    return config_dir() / "config.json"


def reports_dir() -> Path:
    return state_dir() / "reports"


def launch_log() -> Path:
    return state_dir() / "launches.jsonl"


def claude_projects_dir() -> Path:
    return home() / ".claude" / "projects"


def ensure_state() -> None:
    state_dir().mkdir(parents=True, exist_ok=True)
    reports_dir().mkdir(parents=True, exist_ok=True)


def default_config() -> dict[str, Any]:
    return {
        "policy": {
            "auto_approve_until": DEFAULT_AUTO_APPROVE_UNTIL,
            "critical_requires_human": True,
        },
        "tools": {
            "claude": {"enabled": True, "binary": "claude"},
            "codex": {"enabled": True, "binary": "codex"},
        },
        "whatsapp": {
            "provider": "meta_cloud_api",
            "enabled": False,
        },
    }


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return default_config()
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default_config()

    config = default_config()
    for section, value in loaded.items():
        if isinstance(value, dict) and isinstance(config.get(section), dict):
            config[section].update(value)
        else:
            config[section] = value
    return config


def save_config(config: dict[str, Any]) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    with config_path().open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def auto_approves(severity: str, ceiling: str) -> bool:
    if severity == "critical":
        return False
    return SEVERITY_ORDER.index(severity) <= SEVERITY_ORDER.index(ceiling)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iter_jsonl(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return
    except PermissionError:
        return


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    ensure_state()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def resolve_claude_binary() -> str:
    configured = os.environ.get("AUTOCRUNCH_CLAUDE_BIN")
    if configured:
        return configured
    found = shutil.which("claude")
    if found:
        return found
    fallback = home() / ".local" / "bin" / "claude"
    return str(fallback)


def command_run(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode == "bypassPermissions" and not args.i_understand_risk:
        print(
            "Refusing bypassPermissions without --i-understand-risk. "
            "Use this only in a sandbox or throwaway dev environment.",
            file=sys.stderr,
        )
        return 2

    cwd = Path.cwd().resolve()
    claude_bin = resolve_claude_binary()
    passthrough_args = list(args.claude_args)
    if passthrough_args and passthrough_args[0] == "--":
        passthrough_args = passthrough_args[1:]

    claude_args = [claude_bin, "--permission-mode", mode, "--add-dir", str(cwd)]
    claude_args.extend(passthrough_args)

    append_jsonl(
        launch_log(),
        {
            "timestamp": utc_now().isoformat(),
            "cwd": str(cwd),
            "mode": mode,
            "claude_args": passthrough_args,
        },
    )

    os.execvp(claude_bin, claude_args)
    return 127


def extract_tool_names(message: Any) -> list[str]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    names: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_use":
            name = item.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def command_heads(message: Any) -> list[str]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    heads: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("name") != "Bash":
            continue
        command = (item.get("input") or {}).get("command")
        if not isinstance(command, str):
            continue
        parts = command.strip().split()
        if parts:
            heads.append(parts[0])
    return heads


def project_from_jsonl(path: Path) -> str:
    try:
        return path.relative_to(claude_projects_dir()).parts[0]
    except Exception:
        return "unknown"


def build_summary(days: int) -> tuple[str, Path]:
    ensure_state()
    now = utc_now()
    start = now - dt.timedelta(days=days)
    local_date = dt.datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir() / f"weekly-{local_date}.md"

    launches = []
    for item in iter_jsonl(launch_log()):
        seen_at = parse_time(item.get("timestamp"))
        if seen_at and start <= seen_at <= now:
            launches.append(item)

    sessions = 0
    events = 0
    tool_counts: Counter[str] = Counter()
    command_counts: Counter[str] = Counter()
    project_counts: Counter[str] = Counter()
    latest_by_project: dict[str, dt.datetime] = {}

    for raw_path in glob.glob(str(claude_projects_dir() / "**" / "*.jsonl"), recursive=True):
        path = Path(raw_path)
        saw_recent = False
        latest_time: dt.datetime | None = None
        project = project_from_jsonl(path)

        for event in iter_jsonl(path):
            event_time = parse_time(event.get("timestamp"))
            if event_time is None or not (start <= event_time <= now):
                continue
            saw_recent = True
            events += 1
            latest_time = max(latest_time, event_time) if latest_time else event_time
            message = event.get("message")
            tool_counts.update(extract_tool_names(message))
            command_counts.update(command_heads(message))

        if saw_recent:
            sessions += 1
            project_counts[project] += 1
            if latest_time and (project not in latest_by_project or latest_time > latest_by_project[project]):
                latest_by_project[project] = latest_time

    launch_dirs = Counter(str(item.get("cwd", "unknown")) for item in launches)
    mode_counts = Counter(str(item.get("mode", "unknown")) for item in launches)

    lines = [
        f"# Auto-crunch Weekly Summary - {local_date}",
        "",
        f"Window: {start.date().isoformat()} to {now.date().isoformat()} UTC",
        "",
        "## Auto-crunch Launches",
        f"- Total launches: {len(launches)}",
    ]

    for mode, count in mode_counts.most_common():
        lines.append(f"- Mode `{mode}`: {count}")

    if launch_dirs:
        lines.append("")
        lines.append("## Launch Directories")
        for cwd, count in launch_dirs.most_common(10):
            lines.append(f"- {count} launch(es): `{cwd}`")

    lines.extend(
        [
            "",
            "## Claude Sessions",
            f"- Recent session files: {sessions}",
            f"- Recent transcript events: {events}",
            "",
            "## Top Projects",
        ]
    )

    if project_counts:
        for project, count in project_counts.most_common(10):
            latest = latest_by_project.get(project)
            latest_text = latest.isoformat() if latest else "unknown"
            lines.append(f"- {count} session(s): `{project}` latest `{latest_text}`")
    else:
        lines.append("- No recent Claude project sessions found.")

    lines.append("")
    lines.append("## Tool Usage")
    if tool_counts:
        for tool, count in tool_counts.most_common(20):
            lines.append(f"- {tool}: {count}")
    else:
        lines.append("- No tool usage found.")

    lines.append("")
    lines.append("## Bash Command Heads")
    if command_counts:
        for command, count in command_counts.most_common(20):
            lines.append(f"- `{command}`: {count}")
    else:
        lines.append("- No Bash commands found.")

    lines.extend(
        [
            "",
            "## Notes",
            "- This report omits full prompts, full command bodies, and file contents.",
            "- Default `autocrunch run` uses Claude Code `--permission-mode auto`.",
            "",
        ]
    )

    text = "\n".join(lines)
    report_path.write_text(text, encoding="utf-8")
    return text, report_path


def command_summary(args: argparse.Namespace) -> int:
    text, report_path = build_summary(args.days)
    if args.print:
        print(text)
    else:
        print(report_path)
    return 0


def launch_agent_path() -> Path:
    return home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def current_executable() -> str:
    return str(Path(sys.argv[0]).resolve())


def plist_text(hour: int, minute: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>{current_executable()}</string>
    <string>summary</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Minute</key>
    <integer>{minute}</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>{state_dir()}/weekly-summary.out.log</string>

  <key>StandardErrorPath</key>
  <string>{state_dir()}/weekly-summary.err.log</string>
</dict>
</plist>
"""


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def run_launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def command_install_scheduler(args: argparse.Namespace) -> int:
    if platform.system() != "Darwin":
        print("Scheduler install is currently supported only on macOS.", file=sys.stderr)
        return 2

    ensure_state()
    path = launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist_text(args.hour, args.minute), encoding="utf-8")

    run_launchctl("bootout", launchctl_domain(), str(path))
    result = run_launchctl("bootstrap", launchctl_domain(), str(path))
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        print(f"Wrote plist to {path}, but launchctl could not load it.", file=sys.stderr)
        return result.returncode

    print(f"Installed weekly summary LaunchAgent: {path}")
    return 0


def command_uninstall_scheduler(_: argparse.Namespace) -> int:
    path = launch_agent_path()
    run_launchctl("bootout", launchctl_domain(), str(path))
    if path.exists():
        path.unlink()
    print("Uninstalled Auto-crunch weekly summary scheduler.")
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    claude_bin = resolve_claude_binary()
    print(f"Auto-crunch state: {state_dir()}")
    print(f"Config: {config_path()}")
    print(f"Reports: {reports_dir()}")
    print(f"Auto-approve until: {config['policy']['auto_approve_until']}")
    print(f"Claude binary: {claude_bin}")
    print(f"Claude found: {'yes' if Path(claude_bin).exists() or shutil.which(claude_bin) else 'no'}")
    print(f"Codex found: {'yes' if shutil.which('codex') else 'no'}")
    print(f"Platform: {platform.system()} {platform.release()}")
    if platform.system() == "Darwin":
        path = launch_agent_path()
        print(f"LaunchAgent plist: {path}")
        result = run_launchctl("print", f"{launchctl_domain()}/{LABEL}")
        print(f"LaunchAgent loaded: {'yes' if result.returncode == 0 else 'no'}")
    return 0


def command_policy_init(_: argparse.Namespace) -> int:
    if config_path().exists():
        print(f"Config already exists: {config_path()}")
        return 0
    save_config(default_config())
    print(f"Wrote default config: {config_path()}")
    return 0


def command_policy_show(_: argparse.Namespace) -> int:
    print(json.dumps(load_config(), indent=2))
    return 0


def command_policy_set(args: argparse.Namespace) -> int:
    config = load_config()
    config["policy"]["auto_approve_until"] = args.auto_approve_until
    save_config(config)
    print(f"Auto-approve ceiling set to: {args.auto_approve_until}")
    if args.auto_approve_until == "high":
        print("High-severity actions may be auto-approved. Critical actions still require a human.")
    return 0


def command_policy_explain(_: argparse.Namespace) -> int:
    config = load_config()
    ceiling = config["policy"]["auto_approve_until"]
    print(f"Current auto-approve ceiling: {ceiling}")
    print()
    for severity in SEVERITY_ORDER:
        decision = "auto-approve" if auto_approves(severity, ceiling) else "ask/deny"
        print(f"{severity}: {decision}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocrunch",
        description="Terminal helper for low-friction Claude Code sessions and weekly summaries.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Start Claude Code in the current project.")
    run_parser.add_argument(
        "--mode",
        choices=["auto", "acceptEdits", "dontAsk", "manual", "bypassPermissions"],
        default=os.environ.get("AUTOCRUNCH_PERMISSION_MODE", "auto"),
        help="Claude Code permission mode. Default: auto.",
    )
    run_parser.add_argument(
        "--i-understand-risk",
        action="store_true",
        help="Required when using --mode bypassPermissions.",
    )
    run_parser.add_argument("claude_args", nargs=argparse.REMAINDER, help="Arguments passed to claude.")
    run_parser.set_defaults(func=command_run)

    summary_parser = sub.add_parser("summary", help="Write a weekly markdown summary.")
    summary_parser.add_argument("--days", type=int, default=7, help="Number of days to include.")
    summary_parser.add_argument("--print", action="store_true", help="Print the report instead of only the path.")
    summary_parser.set_defaults(func=command_summary)

    scheduler_parser = sub.add_parser("install-scheduler", help="Install the macOS Monday summary job.")
    scheduler_parser.add_argument("--hour", type=int, default=DEFAULT_REPORT_HOUR)
    scheduler_parser.add_argument("--minute", type=int, default=DEFAULT_REPORT_MINUTE)
    scheduler_parser.set_defaults(func=command_install_scheduler)

    uninstall_parser = sub.add_parser("uninstall-scheduler", help="Remove the macOS summary job.")
    uninstall_parser.set_defaults(func=command_uninstall_scheduler)

    doctor_parser = sub.add_parser("doctor", help="Print setup diagnostics.")
    doctor_parser.set_defaults(func=command_doctor)

    policy_parser = sub.add_parser("policy", help="Manage approval policy.")
    policy_sub = policy_parser.add_subparsers(dest="policy_command", required=True)

    policy_init = policy_sub.add_parser("init", help="Create the default config file.")
    policy_init.set_defaults(func=command_policy_init)

    policy_show = policy_sub.add_parser("show", help="Print the active config.")
    policy_show.set_defaults(func=command_policy_show)

    policy_set = policy_sub.add_parser("set", help="Set the auto-approve severity ceiling.")
    policy_set.add_argument(
        "--auto-approve-until",
        choices=["low", "medium", "high"],
        required=True,
        help="Highest severity level Auto-crunch may approve without asking.",
    )
    policy_set.set_defaults(func=command_policy_set)

    policy_explain = policy_sub.add_parser("explain", help="Explain the current approval behavior.")
    policy_explain.set_defaults(func=command_policy_explain)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
