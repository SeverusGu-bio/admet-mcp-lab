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

## What I built

Filled in the three lab stubs in `src/starter_server.py` and added
input validation and structured logging on top.

- **Tool — `compute_absorption_profile(smiles)`**: parsed the SMILES,
  computed MW, logP, TPSA, HBD, HBA, and rotatable bonds with RDKit,
  then ran Lipinski (MW≤500, logP≤5, HBD≤5, HBA≤10), Veber (rotb≤10,
  TPSA≤140), and Egan (logP≤5.88, TPSA≤131.6). Each rule returns
  pass/fail with the specific violations listed. Rolled the three
  results into an overall verdict: `favorable` (0 fails), `borderline`
  (1 fail), `poor` (≥2 fails). Tagged descriptors as `experimental`,
  rule outcomes as `rule_based`, and the verdict as `heuristic`. Wrote
  the docstring as instructions a careful junior chemist could follow.
  Verified aspirin → `favorable`, azithromycin → `poor`.
- **Resource — `compound://{drug_id}`**: SQLite lookup by DrugBank-style
  id (e.g. `DB00945`), returning the same JSON shape as
  `reference://{name}`. On a miss it returns a JSON object with an
  `error` field rather than raising, so Claude keeps going.
- **Prompt — `admet_triage(compound_identifier, therapeutic_context, concerns)`**:
  multi-paragraph instruction that walks the model through resolving
  the compound via a resource, calling both ADMET tools, tagging every
  finding by confidence level, and closing with a medicinal-chemist
  recommendation tied back to the supplied context and concerns.

For the security/observability rubric I added a `validate_smiles_input`
helper (rejects non-strings, empty/whitespace input, and SMILES over
500 chars, with the error message naming the failed check) and wired
it into both tools. `compute_absorption_profile` also emits a single
structured log line per call — `tool=... compound=... verdict=...
elapsed_ms=...` — that greps cleanly during a Scenario 2 multi-call run.

The starter test suite (`uv run pytest -q`) still passes 7/7.

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
