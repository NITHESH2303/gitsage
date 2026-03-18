"""MCP server for gitsage — exposes Git AI tools over stdio (JSON-RPC 2.0).

Connect from Claude Desktop, Cursor, or any MCP-compatible client.
Run:  gitsage-mcp
"""

from __future__ import annotations

import json
import subprocess
import sys

from gitsage import client, prompts, safety

TOOLS = [
    {
        "name": "git_commit_message",
        "description": (
            "Generate a Conventional Commit message from a staged diff. "
            "Pass `repo_path` to auto-read the staged diff, or pass `diff` directly. "
            "Set `include_body` to true for a bullet-point body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repo — used to auto-fetch the staged diff if `diff` is not provided"},
                "diff": {"type": "string", "description": "Output of `git diff --staged` (optional if repo_path is given)"},
                "include_body": {"type": "boolean", "description": "Include a bullet-point body", "default": False},
            },
        },
    },
    {
        "name": "git_pr_description",
        "description": (
            "Generate a PR description (Summary / Changes / Notes) from a commit log. "
            "Pass `repo_path` to auto-fetch the last 20 commits, or pass `commits` directly."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repo — used to auto-fetch commits if `commits` is not provided"},
                "commits": {"type": "string", "description": "Output of `git log --oneline` (optional if repo_path is given)"},
            },
        },
    },
    {
        "name": "git_release_notes",
        "description": (
            "Generate release notes grouped by Features / Bug Fixes / Other from a commit log. "
            "Pass `repo_path` to auto-fetch recent commits, or pass `commits` directly."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repo — used to auto-fetch commits if `commits` is not provided"},
                "commits": {"type": "string", "description": "Output of `git log --oneline v1.0..HEAD` (optional if repo_path is given)"},
            },
        },
    },
    {
        "name": "git_suggest_commands",
        "description": "Suggest safe git commands for a plain-English task description.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What you want to accomplish, e.g. 'undo last commit but keep changes'"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "git_branch_name",
        "description": "Generate a short git branch name from a task description (feat/, fix/, chore/, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Task or feature description"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "git_status",
        "description": "Return the current `git status` of the repository at the given path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_staged_diff",
        "description": "Return the staged diff (`git diff --staged`) for the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_add",
        "description": (
            "Stage files for commit (`git add`). "
            "Pass a list of paths to stage specific files, or omit to stage everything (`.`)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file/directory paths to stage. Defaults to ['.'] (everything).",
                    "default": ["."],
                },
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_fetch",
        "description": (
            "Fetch from a remote (`git fetch`). "
            "Useful before checking out a branch that may only exist on the remote."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "remote": {"type": "string", "description": "Remote to fetch from (default: origin)", "default": "origin"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_branch_create",
        "description": (
            "Create and checkout a branch. "
            "If the branch already exists on the remote but not locally, fetches it and checks it out. "
            "If it doesn't exist anywhere, creates a new local branch (`git checkout -b`)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "branch_name": {"type": "string", "description": "Name of the branch to create or checkout"},
                "remote": {"type": "string", "description": "Remote to fetch from if branch not found locally (default: origin)", "default": "origin"},
            },
            "required": ["repo_path", "branch_name"],
        },
    },
    {
        "name": "git_commit",
        "description": (
            "Commit staged changes with the given message (`git commit -m`). "
            "Use `git_add` to stage files first, and `git_commit_message` to generate a message."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "message": {"type": "string", "description": "Commit message (Conventional Commit format recommended)"},
            },
            "required": ["repo_path", "message"],
        },
    },
    {
        "name": "git_push",
        "description": (
            "Push the current branch to a remote (`git push`). "
            "Defaults to `origin` and the current branch. "
            "Uses `--set-upstream` automatically if the branch has no upstream yet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "remote": {"type": "string", "description": "Remote name (default: origin)", "default": "origin"},
                "branch": {"type": "string", "description": "Branch to push (default: current branch)"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_pull",
        "description": "Pull latest changes from a remote (`git pull`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "remote": {"type": "string", "description": "Remote name (default: origin)", "default": "origin"},
                "branch": {"type": "string", "description": "Branch to pull (default: current branch)"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_log",
        "description": "Return the commit history for the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "count": {"type": "integer", "description": "Number of commits to show (default: 10)", "default": 10},
                "oneline": {"type": "boolean", "description": "Use --oneline format (default: true)", "default": True},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "git_stash",
        "description": "Manage the git stash (save, pop, or list stashed changes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repository"},
                "action": {
                    "type": "string",
                    "enum": ["save", "pop", "list"],
                    "description": "Stash action: 'save' stashes changes, 'pop' restores the latest stash, 'list' shows all stashes.",
                },
                "message": {"type": "string", "description": "Optional description for 'save' action"},
            },
            "required": ["repo_path", "action"],
        },
    },
]


def _ai(prompt: str, model: str = client.DEFAULT_MODEL) -> str:
    try:
        return client.generate(prompt, model=model)
    except Exception as exc:
        return f"[gitsage error] {exc}"


def _git(args: list[str], cwd: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return (result.stdout + result.stderr).strip()


def _call_tool(name: str, inputs: dict) -> str:
    if name == "git_commit_message":
        diff = inputs.get("diff") or ""
        if not diff and inputs.get("repo_path"):
            diff = _git(["git", "diff", "--staged"], inputs["repo_path"])
        include_body = inputs.get("include_body", False)
        response = _ai(prompts.commit(diff, include_body=include_body))
        flagged = safety.scan(response)
        if flagged:
            response += "\n\n" + safety.format_warning(flagged)
        return response

    if name == "git_pr_description":
        commits = inputs.get("commits") or ""
        if not commits and inputs.get("repo_path"):
            commits = _git(["git", "log", "--oneline", "-n20"], inputs["repo_path"])
        return _ai(prompts.pr_description(commits))

    if name == "git_release_notes":
        commits = inputs.get("commits") or ""
        if not commits and inputs.get("repo_path"):
            commits = _git(["git", "log", "--oneline", "-n50"], inputs["repo_path"])
        return _ai(prompts.release_notes(commits))

    if name == "git_suggest_commands":
        response = _ai(prompts.suggest_commands(inputs.get("task", "")))
        flagged = safety.scan(response)
        if flagged:
            response += "\n\n" + safety.format_warning(flagged)
        return response

    if name == "git_branch_name":
        return _ai(prompts.branch_name(inputs.get("description", "")))

    if name == "git_status":
        return _git(["git", "status"], inputs["repo_path"])

    if name == "git_staged_diff":
        return _git(["git", "diff", "--staged"], inputs["repo_path"])

    if name == "git_add":
        paths = inputs.get("paths") or ["."]
        return _git(["git", "add"] + paths, inputs["repo_path"])

    if name == "git_fetch":
        remote = inputs.get("remote", "origin")
        return _git(["git", "fetch", remote], inputs["repo_path"])

    if name == "git_branch_create":
        repo_path = inputs["repo_path"]
        branch = inputs["branch_name"]
        remote = inputs.get("remote", "origin")
        # Try creating the branch locally first
        result = _git(["git", "checkout", "-b", branch], repo_path)
        if "fatal" in result or "error" in result.lower():
            # Branch may exist on remote — fetch and checkout tracking branch
            _git(["git", "fetch", remote], repo_path)
            result = _git(["git", "checkout", "-b", branch, f"{remote}/{branch}"], repo_path)
        return result

    if name == "git_commit":
        message = inputs["message"]
        result = _git(["git", "commit", "-m", message], inputs["repo_path"])
        flagged = safety.scan(result)
        if flagged:
            result += "\n\n" + safety.format_warning(flagged)
        return result

    if name == "git_push":
        repo_path = inputs["repo_path"]
        remote = inputs.get("remote", "origin")
        branch = inputs.get("branch")
        if not branch:
            branch = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_path)
        # Use --set-upstream if branch has no upstream tracking ref
        tracking = _git(["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], repo_path)
        if "fatal" in tracking or "no upstream" in tracking.lower():
            args = ["git", "push", "--set-upstream", remote, branch]
        else:
            args = ["git", "push", remote, branch]
        return _git(args, repo_path)

    if name == "git_pull":
        repo_path = inputs["repo_path"]
        remote = inputs.get("remote", "origin")
        branch = inputs.get("branch")
        args = ["git", "pull", remote] + ([branch] if branch else [])
        return _git(args, repo_path)

    if name == "git_log":
        repo_path = inputs["repo_path"]
        count = inputs.get("count", 10)
        oneline = inputs.get("oneline", True)
        args = ["git", "log", f"-n{count}"]
        if oneline:
            args.append("--oneline")
        return _git(args, repo_path)

    if name == "git_stash":
        repo_path = inputs["repo_path"]
        action = inputs["action"]
        if action == "save":
            message = inputs.get("message")
            args = ["git", "stash", "save"] + ([message] if message else [])
        elif action == "pop":
            args = ["git", "stash", "pop"]
        else:  # list
            args = ["git", "stash", "list"]
        return _git(args, repo_path)

    return f"Unknown tool: {name}"


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gitsage", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        inputs = params.get("arguments", {})
        text = _call_tool(tool_name, inputs)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(msg)
        if response is not None:
            _send(response)
