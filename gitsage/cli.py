"""gitsage — local Git AI assistant (Ollama + SmolLM2).

Usage:
    gitsage commit --stage --commit --push
    git diff --staged              | gitsage commit
    git diff --staged              | gitsage commit --body
    git log -5 --oneline           | gitsage pr
    git log --oneline v1.0..HEAD   | gitsage release
    echo "squash last 3 commits"   | gitsage suggest
    echo "add OAuth login"         | gitsage branch --create
    gitsage status
    gitsage pull
    gitsage stash --save / --pop / --list
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap

from gitsage import client, prompts, safety

_MAX_DIFF_CHARS = 12_000


def _truncate_diff(diff: str) -> str:
    if len(diff) <= _MAX_DIFF_CHARS:
        return diff
    kept = diff[:_MAX_DIFF_CHARS]
    dropped = len(diff) - _MAX_DIFF_CHARS
    print(
        f"[gitsage] Diff is large ({len(diff):,} chars). "
        f"Truncated to {_MAX_DIFF_CHARS:,} chars ({dropped:,} dropped). "
        "For very large changesets, consider committing in smaller batches.",
        file=sys.stderr,
    )
    return kept + f"\n\n... [diff truncated: {dropped} chars omitted] ..."


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitsage",
        description="Local Git AI assistant (Ollama + SmolLM2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              gitsage commit --stage --commit --push
              git diff --staged              | gitsage commit
              git log -5 --oneline           | gitsage pr
              git log --oneline v1.0..HEAD   | gitsage release
              echo "squash last 3 commits"   | gitsage suggest
              echo "add OAuth login"         | gitsage branch --create
              gitsage status
              gitsage pull
              gitsage stash --list
        """),
    )

    parser.add_argument(
        "mode",
        choices=["commit", "pr", "release", "suggest", "branch", "status", "pull", "stash"],
        metavar="MODE",
        help=(
            "commit   AI: generate Conventional Commit message from diff\n"
            "pr       AI: PR description from commit log\n"
            "release  AI: release notes from commit log\n"
            "suggest  AI: suggest safe git commands from English\n"
            "branch   AI: generate branch name from description\n"
            "status   show git status\n"
            "pull     git pull with confirmation\n"
            "stash    manage stash (--save / --pop / --list)"
        ),
    )
    parser.add_argument("--body", action="store_true", default=False,
                        help="commit: also generate a bullet-point body")
    parser.add_argument("--stage", action="store_true", default=False,
                        help="commit: run `git add .` then read the staged diff automatically")
    parser.add_argument("--stage-path", metavar="PATH", default=None,
                        help="commit: stage a specific path instead of `.`")
    parser.add_argument("--commit", action="store_true", default=False,
                        help="commit: run `git commit` with the generated message after confirmation")
    parser.add_argument("--push", action="store_true", default=False,
                        help="commit: run `git push` after committing (requires --commit)")
    parser.add_argument("--create", action="store_true", default=False,
                        help="branch: run `git checkout -b <name>` after confirmation")

    stash_group = parser.add_mutually_exclusive_group()
    stash_group.add_argument("--save", action="store_true", default=False,
                             help="stash: run `git stash push`")
    stash_group.add_argument("--pop", action="store_true", default=False,
                             help="stash: run `git stash pop`")
    stash_group.add_argument("--list", action="store_true", default=False,
                             help="stash: run `git stash list`")

    parser.add_argument("--model", default=client.DEFAULT_MODEL, metavar="NAME",
                        help=f"Ollama model name (default: {client.DEFAULT_MODEL})")
    parser.add_argument("--url", default=client.DEFAULT_URL, metavar="URL",
                        help=f"Ollama base URL (default: {client.DEFAULT_URL})")
    parser.add_argument("--temperature", type=float, default=0.2, metavar="FLOAT",
                        help="Sampling temperature 0.0–1.0 (default: 0.2)")
    return parser


def _confirm(prompt: str) -> bool:
    try:
        with open("/dev/tty") as tty:
            sys.stderr.write(prompt)
            sys.stderr.flush()
            return tty.readline().strip().lower() in ("y", "yes")
    except (OSError, KeyboardInterrupt, EOFError):
        print("\n[gitsage] Aborted.", file=sys.stderr)
        sys.exit(0)


def _run_git(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"[gitsage] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[gitsage] Command failed (exit {result.returncode}).", file=sys.stderr)
        sys.exit(result.returncode)
    return result


def _current_branch() -> str:
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def _read_stdin() -> str:
    if sys.stdin.isatty():
        print(
            "[ERROR] No input — pipe something into gitsage.\n"
            "  Example:  git diff --staged | gitsage commit\n"
            "  Or use:   gitsage commit --stage",
            file=sys.stderr,
        )
        sys.exit(1)
    text = sys.stdin.read().strip()
    if not text:
        print("[ERROR] stdin was empty.", file=sys.stderr)
        sys.exit(1)
    return text


def _stage_and_get_diff(path: str | None) -> str:
    _run_git(["git", "add", path or "."])
    result = subprocess.run(["git", "diff", "--staged"], capture_output=True, text=True)
    diff = result.stdout.strip()
    if not diff:
        print("[gitsage] Nothing staged — no changes to commit.", file=sys.stderr)
        sys.exit(0)
    return diff


def _handle_status() -> None:
    subprocess.run(["git", "status"])


def _handle_pull() -> None:
    branch = _current_branch()
    print(f"[gitsage] Current branch: {branch}", file=sys.stderr)
    if _confirm(f"[gitsage] Run `git pull` on '{branch}'? [y/N] "):
        _run_git(["git", "pull"])
    else:
        print("[gitsage] Pull skipped.", file=sys.stderr)


def _handle_stash(args: argparse.Namespace) -> None:
    if args.list or (not args.save and not args.pop):
        result = subprocess.run(["git", "stash", "list"], capture_output=True, text=True)
        stashes = result.stdout.strip()
        print(stashes if stashes else "[gitsage] Stash is empty.")
        if not args.list:
            print("\n  Use --save to stash current changes.", file=sys.stderr)
            print("  Use --pop  to restore the latest stash.", file=sys.stderr)
    elif args.save:
        if _confirm("[gitsage] Run `git stash push`? This will hide your uncommitted changes. [y/N] "):
            _run_git(["git", "stash", "push"])
        else:
            print("[gitsage] Stash save skipped.", file=sys.stderr)
    elif args.pop:
        result = subprocess.run(["git", "stash", "list"], capture_output=True, text=True)
        if not result.stdout.strip():
            print("[gitsage] Stash is empty — nothing to pop.", file=sys.stderr)
            sys.exit(0)
        if _confirm("[gitsage] Run `git stash pop`? [y/N] "):
            _run_git(["git", "stash", "pop"])
        else:
            print("[gitsage] Stash pop skipped.", file=sys.stderr)


def main() -> None:
    args = _build_parser().parse_args()

    if args.mode == "status":
        _handle_status()
        return
    if args.mode == "pull":
        _handle_pull()
        return
    if args.mode == "stash":
        _handle_stash(args)
        return

    if args.push and not args.commit:
        print("[ERROR] --push requires --commit.", file=sys.stderr)
        sys.exit(1)
    if (args.commit or args.push or args.stage or args.stage_path) and args.mode != "commit":
        print("[ERROR] --stage/--commit/--push are only valid in commit mode.", file=sys.stderr)
        sys.exit(1)
    if args.create and args.mode != "branch":
        print("[ERROR] --create is only valid in branch mode.", file=sys.stderr)
        sys.exit(1)

    if args.mode == "commit" and (args.stage or args.stage_path):
        stdin = _stage_and_get_diff(args.stage_path)
    else:
        stdin = _read_stdin()

    if args.mode == "commit":
        stdin = _truncate_diff(stdin)
        prompt = prompts.commit(stdin, include_body=args.body)
    elif args.mode == "pr":
        prompt = prompts.pr_description(stdin)
    elif args.mode == "release":
        prompt = prompts.release_notes(stdin)
    elif args.mode == "suggest":
        prompt = prompts.suggest_commands(stdin)
    elif args.mode == "branch":
        prompt = prompts.branch_name(stdin)
    else:
        raise ValueError(f"Unknown mode: {args.mode}")

    print(f"[gitsage] mode={args.mode}  model={args.model}", file=sys.stderr)
    print("[gitsage] Sending to Ollama...\n", file=sys.stderr)

    response = client.generate(
        prompt,
        model=args.model,
        url=args.url,
        temperature=args.temperature,
    )

    flagged = safety.scan(response)
    if flagged:
        safety.warn(flagged)

    print(response)

    if args.mode == "commit":
        if args.commit:
            print(f"\n[gitsage] Generated message:\n  {response.splitlines()[0]}", file=sys.stderr)
            if _confirm("[gitsage] Run `git commit` with this message? [y/N] "):
                _run_git(["git", "commit", "-m", response])
            else:
                print("[gitsage] Commit skipped.", file=sys.stderr)
                sys.exit(0)

        if args.push:
            if _confirm("[gitsage] Run `git push`? [y/N] "):
                _run_git(["git", "push"])
            else:
                print("[gitsage] Push skipped.", file=sys.stderr)

    if args.mode == "branch" and args.create:
        branch = response.strip().split()[0]
        print(f"\n[gitsage] Branch name: {branch}", file=sys.stderr)
        if _confirm(f"[gitsage] Run `git checkout -b {branch}`? [y/N] "):
            _run_git(["git", "checkout", "-b", branch])
        else:
            print("[gitsage] Branch creation skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
