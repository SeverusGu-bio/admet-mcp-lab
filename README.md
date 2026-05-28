# ADMET MCP Lab — AICD3

A 120-minute hands-on lab where you build a Model Context Protocol server
that lets Claude triage drug candidates the way a computational chemist
would. By the end of the session, Claude Code will be calling functions
you wrote against a local compound library to evaluate oral absorption
and toxicity liabilities.

## Prerequisites

- Python 3.12 or later
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 18+ (for the MCP Inspector)
- [Claude Code](https://docs.claude.com/en/docs/claude-code/) installed and authenticated
- A working terminal you can keep open during the session

## One-time setup (do this before class)

```bash
git clone <repo-url> admet-mcp-lab
cd admet-mcp-lab

# Create the virtual environment and install dependencies
uv sync

# Build the local compound database
uv run python data/seed_db.py

# Smoke check
uv run pytest -q
```

You should see `7 passed`. If not, flag it in the lab Slack channel.

## What you start with

```
admet-mcp-lab/
├── data/
│   ├── seed_db.py             # builds the SQLite library
│   └── admet_library.db       # 36 FDA-approved drugs (after seed)
├── src/
│   └── starter_server.py      # the file you will edit
├── tests/
│   └── test_smoke.py
├── .mcp.json.example          # template for Claude Code registration
└── pyproject.toml
```

The starter server has **one tool implemented** (`compute_toxicity_alerts`)
and **three stubs** you fill in during the lab: a tool, a resource, and a
prompt.

## What this server exposes

- **Tools**
  - `compute_toxicity_alerts(smiles)` — PAINS + Brenk substructure
    filters and a hERG basic-amine/logP heuristic. Returns a
    `ToxicityProfile` with per-alert confidence levels.
  - `compute_absorption_profile(smiles)` — six RDKit descriptors plus
    Lipinski, Veber, and Egan rule sets. Returns an `AbsorptionProfile`
    with a `favorable` / `borderline` / `poor` overall verdict.
- **Resources**
  - `reference://{name}` — library lookup by drug name (case-insensitive).
  - `compound://{drug_id}` — library lookup by DrugBank-style id, e.g.
    `compound://DB00945`.
- **Prompt**
  - `admet_triage(compound_identifier, therapeutic_context, concerns)` —
    a parameterized triage protocol that orchestrates the resources and
    tools above and demands explicit confidence tagging in the writeup.

Every numeric value, rule outcome, and verdict is tagged with one of
`experimental`, `rule_based`, or `heuristic` so the calling LLM can
weight evidence appropriately. All tools validate input (non-empty
string, ≤ 500 chars) before parsing and emit a single-line structured
log per call for grep-friendly observability.

## During the lab

Follow the student handout your instructor will share. Each phase has a
clear acceptance criterion, so you always know when you can move on.

## Quick command reference

| What | Command |
| ---- | ------- |
| Run the server (stdio) | `uv run src/starter_server.py` |
| Run the server (HTTP) | `MCP_TRANSPORT=http uv run src/starter_server.py` |
| Inspect the server | `npx @modelcontextprotocol/inspector uv run src/starter_server.py` |
| Run smoke tests | `uv run pytest -q` |

## Why this lab matters

Tool calling APIs let an LLM invoke one of your functions. MCP lets your
functions live anywhere, expose themselves through a standard protocol,
and be discovered and composed by any compliant host (Claude Code,
Claude Desktop, Cursor, ChatGPT, others). What you build today is a
real, reusable piece of agentic infrastructure, not a toy.
