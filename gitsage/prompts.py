from __future__ import annotations


def commit(diff: str, *, include_body: bool = False) -> str:
    if include_body:
        output_spec = (
            "Output format:\n"
            "1) ONE subject line only (<=72 chars), Conventional Commits.\n"
            "2) Then a blank line.\n"
            "3) Then up to 3 bullets explaining WHY (not WHAT).\n"
            "No extra text.\n"
        )
    else:
        output_spec = (
            "Output ONE subject line only (<=72 chars), Conventional Commits.\n"
            "No body. No extra text.\n"
        )

    return (
        "Task: Write a Conventional Commit message for the staged diff below.\n"
        f"{output_spec}"
        "Rules:\n"
        "- Do NOT explain what any script does.\n"
        "- Do NOT summarize files.\n"
        "- Do NOT invent changes; use only the diff.\n"
        "- Do NOT use quotes or code blocks.\n\n"
        "STAGED DIFF BEGIN\n"
        f"{diff}\n"
        "STAGED DIFF END\n"
    )


def pr_description(commits: str) -> str:
    return (
        "Generate a Pull Request description in Markdown from the commit list below.\n"
        "Use exactly this format:\n\n"
        "## Summary\n<1–3 sentence overview>\n\n"
        "## Changes\n- <bullet per logical change>\n\n"
        "## Notes\n<optional: breaking changes, migration steps, or leave blank>\n\n"
        f"Commits:\n{commits}"
    )


def release_notes(commits: str) -> str:
    return (
        "Generate concise release notes in Markdown from the commit list below.\n"
        "Group entries under: ### Features, ### Bug Fixes, ### Other Changes.\n"
        "Omit any section that has no entries.\n\n"
        f"Commits:\n{commits}"
    )


def suggest_commands(task: str) -> str:
    return (
        "Suggest safe git commands to accomplish the task described below.\n"
        "Rules: show a --dry-run step first for any destructive operation; "
        "use --force-with-lease instead of --force.\n\n"
        f"Task: {task}"
    )


def branch_name(description: str) -> str:
    return (
        "Generate a short git branch name from the task description below.\n"
        "Rules: lowercase, hyphens only (no spaces or underscores), max 40 chars,\n"
        "prefix with one of: feat/, fix/, chore/, docs/, refactor/.\n"
        "Output ONLY the branch name — nothing else.\n\n"
        f"Task: {description}"
    )
