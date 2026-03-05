from __future__ import annotations

import sys

_DANGEROUS: list[str] = [
    "git push --force ",
    "git reset --hard",
    "git clean -f",
    "git clean -fd",
    "rm -rf",
    "git checkout -- .",
    "git restore .",
    "git branch -D",
]

_BAR = "=" * 62


def scan(text: str) -> list[str]:
    lower = text.lower()
    return [pat for pat in _DANGEROUS if pat.lower() in lower]


def warn(patterns: list[str]) -> None:
    print(f"\n{_BAR}", file=sys.stderr)
    print("  SAFETY WARNING: model output contains potentially", file=sys.stderr)
    print("  destructive git patterns. Review before running:", file=sys.stderr)
    for pat in patterns:
        print(f"    !  {pat}", file=sys.stderr)
    print(_BAR + "\n", file=sys.stderr)


def format_warning(patterns: list[str]) -> str:
    lines = [
        "---",
        "**SAFETY WARNING:** model output contains potentially destructive patterns. Review before running:",
    ]
    for pat in patterns:
        lines.append(f"- `{pat}`")
    return "\n".join(lines)
