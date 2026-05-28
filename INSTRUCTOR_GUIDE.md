# Instructor Guide — ADMET MCP Lab

**Course:** AICD3 Agentic AI Architectures for Drug Discovery
**Session:** 120 minutes, hands-on lab
**Prerequisite:** MCP theory session already delivered (architecture,
primitives, JSON RPC basics, transport types)

---

## At a glance

| Phase | Minutes | Focus | Payoff |
| ----- | ------- | ----- | ------ |
| 0 | 5 | Setup check + finish-line demo | None — set the hook |
| 1 | 20 | Inspector tour of starter server | "My type hints became a schema" |
| 2 | 25 | Build `compute_absorption_profile` | "My function is now an MCP tool" |
| 3 | 15 | Add `compound://{drug_id}` resource | Resources vs. tools clarified |
| 4 | 10 | Add `admet_triage` prompt | Prompts as portable institutional knowledge |
| 5 | 25 | Connect to Claude Code, run agentic scenarios | "Claude is driving my code" |
| 6 | 15 | Hardening exercises | "My server degrades gracefully" |
| 7 | 5 | Demos and close | Reinforce the arc |

Two natural breathing points fall at minute 50 (between Phase 3 and 4)
and minute 90 (between Phase 5 and 6). Use them for questions.

---

## Pre-flight (do the day before)

1. Run a full dry run of the lab on a clean machine. Time yourself.
2. Confirm the npm registry is reachable from the classroom network for
   the Inspector install. If not, mirror the inspector tarball locally.
3. Pre-pull `rdkit` and `mcp` wheels into a local pip cache the students
   can use as fallback.
4. Verify Claude Code authentication works on a fresh machine in the
   classroom.
5. Have the devcontainer fallback ready (see `devcontainer.json` in the
   repo root if you ship one).

## Materials you bring to the room

- The starter repo, cloned and ready on the projector machine
- `_reference_solution.py` (in the repo, not distributed — this is your
  cheat sheet)
- The student handout printed or shared as a doc link
- This guide
- A timer visible to the room

---

## Slide outline (10 slides total, light)

The lab is hands-on, so slides exist only to anchor transitions. Build
in your house deck style. Suggested content:

| # | Title | Body |
| - | ----- | ---- |
| 1 | Today's lab | Build an ADMET server. Connect it to Claude. See agentic orchestration. |
| 2 | Finish line | Live demo of completed Scenario 3 — show the transcript. |
| 3 | Phase 1 | Inspector. Read the wire format. |
| 4 | Phase 2 | Build `compute_absorption_profile`. Specification recap. |
| 5 | Phase 3 | Add a Resource. URI templating. |
| 6 | Phase 4 | Add a Prompt. Portable institutional knowledge. |
| 7 | Phase 5 | Switch transport, register, run scenarios. |
| 8 | Phase 6 | Hardening: validation, logging, empty vs. failure semantics. |
| 9 | What you built today | Same patterns as production MCP servers. |
| 10 | What's next in the course | Bridge to the next session. |

Use the AICD3 visual style. The slides are scaffolding only; do not
lecture from them during hands-on phases.

---

## Phase-by-phase running notes

### Phase 0 — Setup check (5 min)

**Script:**

> "We have 120 minutes. By the end, the natural language prompt I'm
> about to show you will run on the server you wrote yourself. Let's
> get started — pytest passing means you're ready."

Run scenario 3 from the projector against your own pre-built reference
server (running before students arrive). Do not explain it yet. Let the
hook pull them.

While they run pytest, walk the room. Anyone failing should get the
devcontainer immediately rather than spending lab time on environment
debugging.

**Expected failures:**
- Wrong Python version → devcontainer
- `uv` not installed → `curl -LsSf https://astral.sh/uv/install.sh | sh`
- npm proxy issues for the Inspector → defer to Phase 1, run Inspector
  from your machine on the projector

### Phase 1 — Inspector (20 min)

**Script (briefly, then let them work):**

> "MCP runs JSON RPC over a transport. We're going to read the actual
> messages flowing back and forth. The Inspector is a JSON RPC client
> with a UI."

Walk through 1.1 to 1.3 on the projector once, then release them. Spend
the remaining time circulating.

**Things to highlight when you see them at workstations:**
- The auto-generated JSON schema in `inputSchema` — point at it, then
  point at the Python type hints in the source. Make the connection
  explicit.
- The aspirin Brenk flag (phenol_ester). This is the right teaching
  moment to say: "the alert is real. Aspirin is reactive. It is also a
  100-year-old approved drug. **This is exactly why we have confidence
  levels.**"
- The error message when they break the SMILES — read it aloud.

**Common stuck points:**
- Inspector won't open browser → they can also use the `cli` tab in the
  inspector terminal output
- Confused by the difference between `Resources` and `Resource Templates`
  → tell them: templates have `{name}` placeholders, regular resources
  are static URIs. Both are fine.

### Phase 2 — Build the absorption tool (25 min)

This is where the room divides. Pace varies wildly. **Plan to spend 70%
of your floor time here.**

**The 8/16/25 minute checkpoint structure** (in the handout) is for
students. As instructor, walk by every workstation at minute 8 and
minute 16 and ask "where are you?". This both keeps them honest and
flags people who are silently stuck.

**Common stuck points and how to unstick them:**

| Symptom | Likely cause | Fix in one sentence |
| ------- | ------------ | ------------------- |
| "Pydantic complains about `pass`" | reserved word | Use `pass_` as the field name. |
| "My tool doesn't show up in `tools/list`" | forgot the decorator | Add `@mcp.tool()` and restart the server. |
| "Inspector shows the old version of my tool" | server didn't reload | Stop the server (Ctrl+C) and rerun the npx command. The Inspector spawns the server as a subprocess. |
| "RDKit gives a deprecation warning" | normal | Ignore. |
| "TypeError on `Descriptors.MolWt(mol)`" | passed `None` because SMILES failed to parse | Use `parse_smiles_or_raise`. |
| Falling badly behind at minute 16 | overengineering | Open `_reference_solution.py` quietly with them and walk through `evaluate_absorption`. Do not skip the lesson on confidence levels. |

**If the room is ahead of schedule** at the 25 minute mark, do not
expand Phase 2. Move on. The agentic loop in Phase 5 is where the
emotional payoff lives, and you must protect time for it.

### Phase 3 — Add the resource (15 min)

Short. The pattern mirrors `reference://{name}` so most pairs finish
in 8 to 10 minutes.

**Teaching moment to inject when you see students at the Inspector:**
"Notice you didn't add this to any list. The Inspector found it because
the SDK auto-registers from the decorator. Now imagine fifty servers
running in your org. Every host can discover every resource the same
way. **That's the whole point of the M times N becoming M plus N.**"

### Phase 4 — Add the prompt (10 min)

Even shorter. The risk here is students under-investing because it
"feels like just a string". Push back gently:

> "The string lives on the server, not in the client. That means a
> teammate using your server gets your triage protocol for free. It's
> portable institutional knowledge. Write it the way you'd write the
> standing instruction to a careful junior."

### Phase 5 — Connect to Claude Code (25 min)

**This is the emotional peak of the lab.** Protect the time.

Start with everyone running the HTTP transport switch together. Watch
for:

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| "Address already in use" | a previous server is still running | `pkill -f starter_server.py` |
| Claude Code says server "failed to connect" | URL typo in `.mcp.json` | The path is `/mcp` not `/mcp/` (or vice versa depending on SDK version — check the server logs) |
| `/mcp` shows server but no tools | server didn't fully start | Check the server terminal for stack traces |

**For Scenario 1**, run it together on the projector first. Pause after
Claude finishes and trace the tool calls aloud:

> "Notice the order: it read the resource first to get the SMILES, then
> called the absorption tool, then the toxicity tool. It synthesized.
> That's the agentic loop. You wrote the steering wheel."

**For Scenario 2**, let pairs run independently. Walk and watch.

**For Scenario 3**, this is where you want at least 60% of the room to
get a clean run. If a pair's run is messy (Claude gets confused, calls
the wrong tool), that's actually pedagogically valuable — pause with
them and ask: "what would you change about your tool description to
make Claude's job easier?" This is the gateway to good tool design.

### Phase 6 — Hardening (15 min)

Three exercises, students pick two. Don't lecture. Walk and ask
questions.

**The most valuable observation to surface in 6.C:** when Claude calls
a tool that returns an empty list, it tends to keep working. When a
tool errors, Claude's behaviour is much more variable — sometimes it
recovers, sometimes it abandons the task. **The takeaway: empty is a
valid response, not a failure. Design your tools to distinguish them.**

### Phase 7 — Showcase (5 min)

Pre-select two pairs during Phase 5 whose Scenario 3 ran cleanly. Have
them screen-share. Do not let the demos run long; this is the cool-down,
not a deep dive.

Close with a one-sentence bridge to the next course session.

---

## Recovery scripts (use verbatim if you blank under pressure)

### When a student is stuck on absorption past minute 18

> "Open `src/_reference_solution.py`. Look at `evaluate_absorption`.
> Don't copy it line by line — read it, close it, and write your own.
> The point is the pattern, not the prose."

### When the room can't get the Inspector to open

> "We're going to do Phase 1 from my projector. Watch the requests, I'll
> narrate. You can run the Inspector yourself any time after lab — it's
> in your handout."

### When Claude Code refuses to connect

> "Three things to check: server is running, URL in .mcp.json matches
> the server's actual port, and there's no trailing slash mismatch.
> 90% of the time it's the trailing slash."

### When a pair's Scenario 3 produces nonsense

> "Look at your tool's docstring. Claude reads it as instructions. If a
> careful junior couldn't tell from the docstring when to use this tool,
> Claude can't either. Rewrite the first line and try again."

---

## Reference solutions

`src/_reference_solution.py` contains complete implementations of:

- `compute_absorption_profile`
- `compound://{drug_id}` resource
- `admet_triage` prompt

Use only as a fallback. If you must show one publicly, do it after at
least 60% of pairs have finished the equivalent stub themselves.

---

## Common end-of-lab questions and good answers

**"Why MCP instead of a normal HTTP API?"**
Discovery, schema standardization, and host portability. The same
server works in Claude Code, Claude Desktop, Cursor, and ChatGPT
without modification.

**"How does this differ from OpenAI's tool calling?"**
Tool calling is what the LLM uses inside one turn. MCP is the protocol
for how the host advertises what tools exist, where they live, and how
to invoke them. They compose: tool calling consumes MCP-discovered tools.

**"Is this production-ready?"**
The patterns are. Your server is not yet — for production you'd add
OAuth 2.1 auth, rate limiting, observability beyond logs, supply chain
controls on dependencies, and Server Cards at `.well-known`. You
covered all of those in the theory session.

**"Can I use this with my own data?"**
Yes. Replace the `seed_db.py` with your library. Adjust the descriptors
or rules. The MCP scaffolding stays the same.

---

## Pre-class checklist

- [ ] Repo cloned on projector machine
- [ ] Reference server pre-built and running for Phase 0 demo
- [ ] Slides loaded
- [ ] Timer visible
- [ ] Devcontainer fallback tested
- [ ] Claude Code logged in on projector
- [ ] Inspector tested on projector
- [ ] Two known-clean Scenario 3 transcripts ready to show if no
      student demo materializes
- [ ] Student handout shared (link or print)
- [ ] Lab Slack channel pinned for setup issues

## Post-class

Collect the deliverables (repo + recording). Run `pytest` against each
submission for the correctness portion of the rubric. Spot-check three
recordings for the agentic loop quality. Keep the two cleanest as
exemplars for next year.
