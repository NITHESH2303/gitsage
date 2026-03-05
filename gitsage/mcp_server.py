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
            "Pass the output of `git diff --staged` as `diff`. "
            "Set `include_body` to true for bullet-point body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff": {"type": "string", "description": "Output of `git diff --staged`"},
                "include_body": {"type": "boolean", "description": "Include a bullet-point body", "default": False},
            },
            "required": ["diff"],
        },
    },
    {
        "name": "git_pr_description",
        "description": "Generate a PR description (Summary / Changes / Notes) from a commit log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "commits": {"type": "string", "description": "Output of `git log --oneline`"},
            },
            "required": ["commits"],
        },
    },
    {
        "name": "git_release_notes",
        "description": "Generate release notes grouped by Features / Bug Fixes / Other from a commit log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "commits": {"type": "string", "description": "Output of `git log --oneline v1.0..HEAD`"},
            },
            "required": ["commits"],
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
        diff = inputs.get("diff", "")
        include_body = inputs.get("include_body", False)
        response = _ai(prompts.commit(diff, include_body=include_body))
        flagged = safety.scan(response)
        if flagged:
            response += "\n\n" + safety.format_warning(flagged)
        return response

    if name == "git_pr_description":
        return _ai(prompts.pr_description(inputs.get("commits", "")))

    if name == "git_release_notes":
        return _ai(prompts.release_notes(inputs.get("commits", "")))

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
