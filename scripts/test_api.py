#!/usr/bin/env python3
"""Test the gitsage Ollama API.

Usage:
    python scripts/test_api.py              # run all tests
    python scripts/test_api.py commit       # run one test
    python scripts/test_api.py commit pr    # run specific tests
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

URL = "http://localhost:11434/api/generate"
MODEL = "gitsage"

TESTS: dict[str, dict] = {
    "ping": {
        "label": "Smoke test",
        "prompt": "Reply with exactly one word: READY",
    },
    "commit": {
        "label": "Commit message from diff",
        "options": {"temperature": 0.2},
        "prompt": (
            "Task: Write a Conventional Commit message for the staged diff below.\n"
            "Output ONE subject line only (<=72 chars), Conventional Commits.\n"
            "No body. No extra text.\n\n"
            "STAGED DIFF BEGIN\n"
            "diff --git a/gitsage/cli.py b/gitsage/cli.py\n"
            "--- a/gitsage/cli.py\n"
            "+++ b/gitsage/cli.py\n"
            "@@ -1,4 +1,8 @@\n"
            "+import subprocess\n"
            " import sys\n"
            "+\n"
            "+def _run_git(cmd):\n"
            "+    subprocess.run(cmd)\n"
            "STAGED DIFF END\n"
        ),
    },
    "commit_body": {
        "label": "Commit message with body",
        "options": {"temperature": 0.2},
        "prompt": (
            "Task: Write a Conventional Commit message for the staged diff below.\n"
            "Output format:\n"
            "1) ONE subject line only (<=72 chars), Conventional Commits.\n"
            "2) Then a blank line.\n"
            "3) Then up to 3 bullets explaining WHY (not WHAT).\n"
            "No extra text.\n\n"
            "STAGED DIFF BEGIN\n"
            "diff --git a/gitsage/safety.py b/gitsage/safety.py\n"
            "+_DANGEROUS = ['git push --force', 'rm -rf']\n"
            "+def scan(text): return [p for p in _DANGEROUS if p in text]\n"
            "STAGED DIFF END\n"
        ),
    },
    "pr": {
        "label": "PR description from commit log",
        "prompt": (
            "Generate a Pull Request description in Markdown from the commit list below.\n"
            "Use exactly this format:\n\n"
            "## Summary\n<1-3 sentence overview>\n\n"
            "## Changes\n- <bullet per logical change>\n\n"
            "## Notes\n<optional: breaking changes or leave blank>\n\n"
            "Commits:\n"
            "feat(cli): add --stage flag to auto-stage files\n"
            "feat(cli): add --commit flag with y/N confirmation\n"
            "feat(cli): add --push flag after commit\n"
            "fix(client): handle URLError gracefully\n"
        ),
    },
    "release": {
        "label": "Release notes",
        "prompt": (
            "Generate concise release notes in Markdown from the commit list below.\n"
            "Group entries under: ### Features, ### Bug Fixes, ### Other Changes.\n"
            "Omit any section that has no entries.\n\n"
            "Commits:\n"
            "feat: add branch mode with AI name generation\n"
            "feat: add stash save/pop/list commands\n"
            "fix: fix pyproject.toml build backend\n"
            "chore: add test_api.py script\n"
        ),
    },
    "suggest": {
        "label": "Suggest git commands",
        "prompt": (
            "Suggest safe git commands to accomplish the task described below.\n"
            "Rules: show a --dry-run step first for any destructive operation; "
            "use --force-with-lease instead of --force.\n\n"
            "Task: undo the last commit but keep the file changes staged"
        ),
    },
    "branch": {
        "label": "Generate branch name",
        "options": {"temperature": 0.1},
        "prompt": (
            "Generate a short git branch name from the task description below.\n"
            "Rules: lowercase, hyphens only (no spaces or underscores), max 40 chars,\n"
            "prefix with one of: feat/, fix/, chore/, docs/, refactor/.\n"
            "Output ONLY the branch name — nothing else.\n\n"
            "Task: add OAuth2 login with Google"
        ),
    },
}

SEP = "─" * 60


def _call(test: dict) -> str:
    payload = json.dumps({
        "model": MODEL,
        "prompt": test["prompt"],
        "stream": False,
        "options": test.get("options", {}),
    }).encode()

    req = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except urllib.error.URLError as exc:
        return f"[ERROR] Cannot reach Ollama at {URL}: {exc}"


def run(names: list[str]) -> None:
    for name in names:
        if name not in TESTS:
            print(f"[SKIP] Unknown test: {name!r}  (choices: {', '.join(TESTS)})")
            continue

        test = TESTS[name]
        print(f"\n{SEP}")
        print(f"  TEST : {name}")
        print(f"  LABEL: {test['label']}")
        print(SEP)
        print("  Sending...", flush=True)
        response = _call(test)
        print("\n  RESPONSE:\n")
        for line in response.splitlines():
            print(f"    {line}")
        print()

    print(SEP)
    print("  Done.")
    print(SEP)


if __name__ == "__main__":
    selected = sys.argv[1:] if len(sys.argv) > 1 else list(TESTS)
    run(selected)
