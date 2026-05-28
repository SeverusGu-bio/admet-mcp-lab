# ADMET MCP Lab — Student Handout

**Course:** AICD3 Agentic AI Architectures for Drug Discovery
**Duration:** 120 minutes
**Format:** Hands-on, paired or solo
**Deliverable:** Your extended `starter_server.py`, a short `README.md`
note describing your tools, and a 90 second screen recording of Claude
Code using your server.

---

## What you will build

By the end of this lab, you will have a working MCP server that exposes:

- **2 tools**: `compute_toxicity_alerts` (provided), `compute_absorption_profile` (you build)
- **2 resources**: `reference://{name}` (provided), `compound://{drug_id}` (you build)
- **1 prompt**: `admet_triage` (you build)

And you will see Claude Code orchestrate all of them in a single natural
language turn.

---

## Phase 0 — Setup check (5 min)

Confirm your environment is ready.

```bash
cd admet-mcp-lab
uv run pytest -q
```

**Acceptance:** `7 passed`. If not, raise your hand.

---

## Phase 1 — Inspect the starter (20 min)

Goal: see the wire format. Open the MCP Inspector against the starter server
and read the actual JSON RPC traffic.

### 1.1 Launch the server under the Inspector

In one terminal:

```bash
npx @modelcontextprotocol/inspector uv run src/starter_server.py
```

The Inspector opens a web UI (usually `http://localhost:6274`).

### 1.2 Discover what the server offers

In the Inspector:

1. Click **Tools** → **List Tools**. You should see `compute_toxicity_alerts`.
2. Expand the tool and look at `inputSchema`. **Notice that this JSON Schema
   was generated automatically from the Python type hints in the source.**
   Open `src/starter_server.py` and find the function signature. Compare.
3. Click **Resources** → **List Templates**. You should see `reference://{name}`.
4. Click **Prompts** → **List Prompts**. The list is empty right now (you
   will add one in Phase 4).

### 1.3 Invoke the tool

Still in the Inspector, click on `compute_toxicity_alerts`, set
`smiles` to `CC(=O)Oc1ccccc1C(=O)O` (aspirin), and run it.

**Look at the raw JSON response.** Notice:
- the `compound` block has the canonical SMILES and the looked-up name
- the `alerts` array contains a Brenk flag (`phenol_ester`)
- every alert has a `confidence` field

### 1.4 Read the resource

In Resources, request `reference://imatinib`. You get a JSON payload with
SMILES, therapeutic class, approval year, and any known ADMET flags.

### 1.5 Break something on purpose

Call `compute_toxicity_alerts` with `smiles` set to `not a real smiles`.
Look at the error response. **Notice it tells you exactly what failed and
suggests what to check.** That clarity matters: when Claude calls your
tool and gets an error, the error message is part of the prompt context
that decides whether Claude recovers gracefully or gives up.

**Acceptance:** you can describe, in one sentence each, what Tools,
Resources, and Prompts do, and what JSON RPC method (`tools/list`,
`tools/call`, `resources/read`, etc.) drives each.

---

## Phase 2 — Build `compute_absorption_profile` (25 min)

Goal: implement an oral absorption tool that applies three classical rule
sets and returns a structured verdict.

### Specification

**Input:** `smiles: str`

**Behaviour:**

1. Parse the SMILES (use the existing `parse_smiles_or_raise` helper).
2. Compute these descriptors via RDKit:
   - molecular weight: `Descriptors.MolWt`
   - logP: `Descriptors.MolLogP`
   - topological polar surface area: `Descriptors.TPSA`
   - hydrogen bond donors: `Descriptors.NumHDonors`
   - hydrogen bond acceptors: `Descriptors.NumHAcceptors`
   - rotatable bonds: `Descriptors.NumRotatableBonds`
3. Apply three rule sets:
   - **Lipinski:** MW ≤ 500, logP ≤ 5, HBD ≤ 5, HBA ≤ 10
   - **Veber:** rotatable bonds ≤ 10, TPSA ≤ 140
   - **Egan:** logP ≤ 5.88, TPSA ≤ 131.6
4. For each rule, return pass/fail and a list of specific violations.
5. Compute an overall verdict:
   - `favorable` if all three pass
   - `borderline` if exactly one fails
   - `poor` if two or more fail
6. Use `confidence`:
   - `experimental` for descriptor values (RDKit is deterministic)
   - `rule_based` for rule pass/fail
   - `heuristic` for the overall verdict

**Output:** define a Pydantic `AbsorptionProfile` model that mirrors the
shape of `ToxicityProfile`.

### Checkpoints

After **8 minutes** you should have:
- the `AbsorptionProfile` and a `RuleResult` model defined
- the function signature with `@mcp.tool()` decorator and a precise docstring

After **16 minutes** you should have:
- all six descriptors computed
- the three rules implemented and producing violation lists

After **25 minutes** you should have:
- the overall verdict logic
- a successful run in the Inspector against aspirin (returns `favorable`)

### Acceptance test

```
Inspector → tools/call compute_absorption_profile
  smiles: "CC(=O)Oc1ccccc1C(=O)O"      → verdict "favorable"
  smiles: "CCC1OC(=O)C(C)C(OC2CC..."  (azithromycin) → verdict "poor"
```

### Hints

- Look at how `compute_toxicity_alerts` is structured. Mirror it.
- Pydantic field name `pass` is reserved in Python. Use `pass_` or alias it.
- Your docstring is what the LLM reads to decide when to call your tool.
  Write it like instructions to a careful junior chemist.

---

## Phase 3 — Add the `compound://{drug_id}` resource (15 min)

Goal: expose the library as queryable read-only data.

### Specification

- URI template: `compound://{drug_id}`
- Look up by `drug_id` (e.g. `DB00945`)
- Return JSON with all columns from the `drugs` table
- On miss, return a JSON object with an `error` field (do not raise)

### Implementation pattern

```python
@mcp.resource("compound://{drug_id}")
def compound_record(drug_id: str) -> str:
    ...
```

Use `get_conn()` for the database connection. Use `json.dumps` for the
return value (resources return strings, not Python objects).

### Acceptance test

In the Inspector, request:
- `compound://DB00945` → returns aspirin data
- `compound://DB99999` → returns `{"error": "..."}`

### Why this matters conceptually

Resources are how you give the LLM **context** without burning tokens on
data the LLM does not need yet. Claude can list resources, decide which
one is relevant, and read just that one. Compare with stuffing the entire
library into the system prompt.

---

## Phase 4 — Add the `admet_triage` prompt (10 min)

Goal: ship a reusable, parameterized instruction template that lives on
the server.

### Specification

```python
@mcp.prompt()
def admet_triage(
    compound_identifier: str,
    therapeutic_context: str,
    concerns: str,
) -> str:
    ...
```

The returned string should instruct the LLM to:

1. Resolve the compound via `reference://` or `compound://`
2. Call both ADMET tools
3. Synthesize a verdict that explicitly distinguishes between
   `experimental`, `rule_based`, and `heuristic` evidence
4. Produce a recommendation in medicinal chemist language

### Acceptance test

In the Inspector, request the prompt with arguments:

```
compound_identifier: "imatinib"
therapeutic_context: "chronic oral dosing in CML"
concerns:            "hepatotoxicity and oral bioavailability"
```

You should get back a multi-paragraph instruction string.

### Why this matters conceptually

Prompts are reusable. A pharmacology team can install your server and
have the same triage protocol available to every analyst, without
copy-pasting prompt text. **Prompts are how organizations ship
institutional knowledge.**

---

## Phase 5 — Connect to Claude Code and run an agentic loop (25 min)

Goal: see Claude orchestrate everything you built.

### 5.1 Switch transport to Streamable HTTP

In one terminal:

```bash
MCP_TRANSPORT=http uv run src/starter_server.py
```

You should see `Started server process` and the server listening on
`http://0.0.0.0:8000/mcp`.

Leave this terminal running.

### 5.2 Register with Claude Code

Copy the example config:

```bash
cp .mcp.json.example .mcp.json
```

Edit `.mcp.json` so the path to your repo is correct, then change the
command block to point at the HTTP transport:

```json
{
  "mcpServers": {
    "admet-oracle": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

In a second terminal, in the same directory:

```bash
claude
```

In the Claude Code prompt, run `/mcp` to confirm `admet-oracle` is
listed and connected.

### 5.3 Run the three agentic scenarios

Try them in order. Each one is more demanding than the last.

**Scenario 1 (single chain):**

> Give me the full ADMET profile of aspirin.

What to watch for: Claude reads `reference://aspirin`, calls both tools,
synthesizes one paragraph.

**Scenario 2 (multi-compound comparison):**

> Compare ibuprofen, naproxen, and celecoxib on oral bioavailability and
> toxicity liabilities. Which would you prefer for chronic dosing?

What to watch for: three reference reads, six tool calls (two per
compound), a comparative table.

**Scenario 3 (library triage with uncertainty reasoning):**

> From the library, identify CNS-directed drugs with favorable absorption
> that also pass the toxicity heuristics. For any that fail, explain the
> confidence level of the failure so I know whether to trust it.

What to watch for: Claude querying the library, iterating ADMET checks,
and explicitly distinguishing rule-based failures from heuristic flags
in its writeup. **This is the payoff moment of the lab.**

### Acceptance

You can describe, watching the Claude Code transcript, exactly which
tool calls Claude made and in what order. If you cannot, ask the LLM to
explain its plan before executing.

---

## Phase 6 — Harden it (15 min)

Pick **two** of the following. Each takes about 5 minutes.

### 6.A Validate input

Add a check that rejects empty SMILES, non-string input, and SMILES
longer than 500 characters with a structured error. Verify in the
Inspector that the error message names which validation failed.

### 6.B Structured logging

Add a log line to `compute_absorption_profile` that records:
`compound name (if known), tool name, execution time in ms,
overall verdict`. Use the existing `log` instance. Run scenario 2 in
Claude Code and grep the server output for your logs.

### 6.C Empty vs. failed semantics

Add a tool `find_in_library(therapeutic_class: str)` that returns a
list of compounds. Test what happens when you ask Claude:
- about a class that has matches (`CNS`)
- about a class that does not (`gene_therapy`)
- when the database file is renamed temporarily

Notice how Claude's behaviour differs across "empty result" vs. "tool
failed". This distinction is what makes a server feel solid in
production.

---

## Phase 7 — Showcase (5 min)

Two pairs will demo their Scenario 3 transcripts. Be ready to share
your screen.

---

## Submission

Push to your GitHub fork:

- `src/starter_server.py` (your version)
- `README.md` updated with a one-paragraph description of your tools
- `recording.mp4` (or a link to a Loom): 90 seconds, showing Scenario 3
  running in Claude Code

## Rubric

| Dimension | Weight |
| --------- | ------ |
| Tool correctness (passes given test SMILES) | 40% |
| Tool design quality (docstrings, error handling, confidence levels) | 30% |
| Security and observability hygiene | 20% |
| README clarity | 10% |

## Stretch goals

If you finish early:

- Add `compute_distribution_profile` with a BBB penetration heuristic
- Add `compute_metabolism_flags` for CYP3A4 and CYP2D6 substrate alerts
- Add a composition tool `compute_full_admet` that internally calls all
  three and returns a unified report
- Package the server as a Docker image
- Publish it to your team's internal PyPI

## A note on what you have built

The server you wrote today is functionally equivalent to what a small
biotech might build to wrap an internal cheminformatics library. The
patterns (typed schemas, confidence levels, separate tools versus
resources versus prompts, transport flexibility) are the same patterns
production MCP servers use. You can take this code, swap the descriptors
for your group's actual scoring functions, and have a real internal tool.
