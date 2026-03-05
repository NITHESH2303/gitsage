# gitsage

Fully local Git workflow assistant powered by **Ollama + SmolLM2 1.7B**.
No cloud calls. No API keys. Runs entirely on your machine.

---

## MCP — connect to Claude Desktop, Cursor, or any AI tool

gitsage exposes an **MCP (Model Context Protocol) server** so any compatible AI assistant
can call its Git tools natively. When you say "commit my changes" in Claude or Cursor,
it delegates to gitsage → Ollama locally. No cloud AI touches your diffs.

### Tools exposed

| Tool | What it does |
|------|-------------|
| `git_commit_message` | Generate a Conventional Commit message from a diff |
| `git_pr_description` | Generate a PR description from a commit log |
| `git_release_notes` | Generate release notes from a commit log |
| `git_suggest_commands` | Suggest safe git commands from plain English |
| `git_branch_name` | Generate a branch name from a task description |
| `git_status` | Return `git status` for a repo path |
| `git_staged_diff` | Return `git diff --staged` for a repo path |

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gitsage": {
      "command": "/path/to/gitsage/.venv/bin/gitsage-mcp"
    }
  }
}
```

Restart Claude Desktop. You'll see gitsage tools appear in the tool picker.

### Cursor

Add to your Cursor MCP config (`.cursor/mcp.json` in your project, or global settings):

```json
{
  "mcpServers": {
    "gitsage": {
      "command": "/path/to/gitsage/.venv/bin/gitsage-mcp"
    }
  }
}
```

### Any other MCP client

The server speaks JSON-RPC 2.0 over stdio — compatible with any MCP client.
Run it directly: `gitsage-mcp` (reads from stdin, writes to stdout).

---

## What it does

| Command | What happens |
|---------|-------------|
| `gitsage commit --stage` | Stages everything, generates a Conventional Commit message |
| `gitsage commit --stage --commit --push` | Stage → AI message → confirm → commit → push |
| `git diff --staged \| gitsage commit` | Generate message from an existing staged diff |
| `git log -5 --oneline \| gitsage pr` | Write a PR description from recent commits |
| `git log --oneline v1.0..HEAD \| gitsage release` | Generate release notes |
| `echo "squash last 3 commits" \| gitsage suggest` | Get safe git commands in plain English |
| `echo "add OAuth login" \| gitsage branch --create` | Generate + checkout a branch name |
| `gitsage status` | `git status` |
| `gitsage pull` | `git pull` with confirmation |
| `gitsage stash --save / --pop / --list` | Stash management |

---

## Setup

### Requirements

- macOS (tested on M2, 16 GB RAM)
- [Ollama](https://ollama.com) installed
- Python 3.8+

### 1. Download the model

```sh
mkdir -p ~/models
curl -L -o ~/models/SmolLM2-1.7B-Instruct-Q4_K_M.gguf \
  "https://huggingface.co/bartowski/SmolLM2-1.7B-Instruct-GGUF/resolve/main/SmolLM2-1.7B-Instruct-Q4_K_M.gguf"
```

### 2. Run setup

```sh
bash scripts/setup.sh
```

This will: patch the Modelfile with the correct model path, start `ollama serve`, register the `gitsage` model, and run a smoke test.

### 3. Install the CLI

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

For global availability:

```sh
pipx install -e /path/to/gitsage
```

---

## CLI reference

```
gitsage MODE [options]

Modes:
  commit    Generate a Conventional Commit message from a diff
  pr        Generate a PR description from a commit log
  release   Generate release notes from a commit log
  suggest   Suggest safe git commands from plain English
  branch    Generate a branch name from a task description
  status    Show git status
  pull      git pull with confirmation
  stash     Stash management

Flags:
  --body          commit: include a bullet-point body (why, not what)
  --stage         commit: run `git add .` before reading the diff
  --stage-path    commit: stage a specific path instead of .
  --commit        commit: run `git commit` after confirmation
  --push          commit: run `git push` after committing (requires --commit)
  --create        branch: run `git checkout -b` after confirmation
  --save/--pop/--list  stash operations
  --model NAME    Ollama model name (default: gitsage)
  --temperature   Sampling temperature 0.0–1.0 (default: 0.2)
```

---

## Using via API (no CLI install needed)

If you want to call gitsage from another project without installing the CLI:

```sh
# Commit message
DIFF=$(git diff --staged)
curl -s http://localhost:11434/api/generate \
  -d "{\"model\":\"gitsage\",\"stream\":false,\"prompt\":\"Write a Conventional Commit subject line (<=72 chars) for this diff. Output only the commit message.\n\n${DIFF}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['response'].strip())"

# PR description
COMMITS=$(git log -10 --oneline)
curl -s http://localhost:11434/api/generate \
  -d "{\"model\":\"gitsage\",\"stream\":false,\"prompt\":\"Generate a PR description (## Summary / ## Changes / ## Notes) from:\n\n${COMMITS}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['response'].strip())"
```

Always use `"role": "user"` when calling `/api/chat`. For `/api/generate`, the system prompt is already baked into the model via the Modelfile.

---

## Model tuning

The default context window is `num_ctx 4096`, which fits most staged diffs.
If you work with very large diffs (mono-repo, many files at once), increase it:

```
# ollama/Modelfile
PARAMETER num_ctx 8192   # ~+400 MB RAM on M2
```

Then re-register: `ollama create gitsage -f ollama/Modelfile`

Other useful tweaks:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `temperature` | 0.2 | Lower = more deterministic messages |
| `num_ctx` | 4096 | Higher = handles larger diffs |
| `repeat_penalty` | 1.1 | Reduces repetitive output |

---

## Guardrails

Every model response is scanned before printing. If any of these patterns appear, a warning is shown:

- `git push --force` → suggests `--force-with-lease`
- `git reset --hard`
- `git clean -f` / `git clean -fd`
- `git checkout -- .` / `git restore .`
- `rm -rf`

Nothing is ever auto-executed without your confirmation.

---

## Project structure

```
gitsage/
├── gitsage/
│   ├── cli.py        # CLI entrypoint
│   ├── client.py     # Ollama HTTP wrapper (stdlib only)
│   ├── prompts.py    # Prompt builders for each mode
│   └── safety.py     # Guardrail scanner
├── ollama/
│   └── Modelfile     # Model config + system prompt
├── scripts/
│   ├── setup.sh      # One-shot setup
│   └── test_api.py   # API smoke tests
└── pyproject.toml
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `connection refused` on port 11434 | Run `ollama serve` |
| `model 'gitsage' not found` | Run `ollama create gitsage -f ollama/Modelfile` |
| Model confused on large diffs | Increase `num_ctx` to 8192 in Modelfile and recreate; or commit in smaller batches |
| Slow responses | Reduce `num_ctx` to 2048 in Modelfile and recreate |
| Output too verbose / off-topic | Lower `temperature` to 0.1 |
| Wrong FROM path in Modelfile | Re-run `scripts/setup.sh` or edit manually and recreate |
| Model not using GPU | Ollama auto-detects Metal on M2; verify with `ollama ps` |
