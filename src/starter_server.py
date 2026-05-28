"""
ADMET MCP Server (starter).

This is the server you will extend during the lab. Out of the box it ships
with one fully implemented tool (compute_toxicity_alerts), one resource
(reference://{name}), and one stub you will fill in (compute_absorption_profile).

Run locally with stdio transport (Phase 1 to 4):
    uv run src/starter_server.py

Or with Streamable HTTP transport (Phase 5):
    MCP_TRANSPORT=http uv run src/starter_server.py

Inspect with:
    npx @modelcontextprotocol/inspector uv run src/starter_server.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

# ---------------------------------------------------------------------------
# Logging: structured, single line, easy to grep during the hardening phase.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
)
log = logging.getLogger("admet")

# ---------------------------------------------------------------------------
# Database access. The SQLite file is built once via data/seed_db.py.
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent.parent / "data" / "admet_library.db"


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} not found. Run 'python data/seed_db.py' first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Filter catalogs (load once at module import; PAINS and Brenk ship with RDKit).
# ---------------------------------------------------------------------------
_pains_params = FilterCatalogParams()
_pains_params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
PAINS_CATALOG = FilterCatalog(_pains_params)

_brenk_params = FilterCatalogParams()
_brenk_params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
BRENK_CATALOG = FilterCatalog(_brenk_params)


# ---------------------------------------------------------------------------
# Response models. Every value carries a confidence level so the LLM can
# reason about how much to trust each piece of evidence.
# ---------------------------------------------------------------------------
ConfidenceLevel = Literal[
    "experimental", "rule_based", "heuristic", "toy_model"
]


class Measurement(BaseModel):
    """A single measured or computed value with its confidence level."""

    value: float | int | bool | str
    confidence: ConfidenceLevel
    source: str = Field(
        description="Brief citation or method, e.g. 'RDKit Descriptors.MolWt'"
    )


class ToxicityAlert(BaseModel):
    """One liability flag raised by a substructure filter or heuristic."""

    name: str
    category: Literal["PAINS", "Brenk", "hERG_heuristic"]
    description: str
    confidence: ConfidenceLevel


class CompoundIdentity(BaseModel):
    smiles: str
    canonical_smiles: str
    canonical_name: str | None = None
    molecular_formula: str | None = None


class ToxicityProfile(BaseModel):
    compound: CompoundIdentity
    alerts: list[ToxicityAlert]
    overall_verdict: str
    interpretation: str
    sources: list[str]


class RuleResult(BaseModel):
    """Outcome of a single oral-absorption rule set against one compound."""

    name: Literal["Lipinski", "Veber", "Egan"]
    pass_: bool = Field(alias="pass")
    violations: list[str]
    confidence: ConfidenceLevel

    model_config = {"populate_by_name": True}


class AbsorptionProfile(BaseModel):
    compound: CompoundIdentity
    descriptors: dict[str, Measurement]
    rules: list[RuleResult]
    overall_verdict: Literal["favorable", "borderline", "poor"]
    interpretation: str
    sources: list[str]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def validate_smiles_input(smiles: object) -> str:
    """Reject obviously bad input before it reaches RDKit.

    Distinguishes the three failure modes so the error message names the
    specific check that failed, which matters when an LLM is reading the
    error to decide whether to retry or give up.
    """
    if not isinstance(smiles, str):
        raise ValueError(
            f"Invalid smiles input: expected str, got {type(smiles).__name__}."
        )
    if not smiles.strip():
        raise ValueError("Invalid smiles input: empty string.")
    if len(smiles) > 500:
        raise ValueError(
            f"Invalid smiles input: length {len(smiles)} exceeds 500-char limit."
        )
    return smiles


def parse_smiles_or_raise(smiles: str) -> Chem.Mol:
    """Parse a SMILES string; raise a clear error if it cannot be parsed."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(
            f"Could not parse SMILES '{smiles}'. "
            "Verify chirality markers and ring closures."
        )
    return mol


def lookup_name(smiles: str) -> str | None:
    """Find the canonical name for a SMILES if it matches a library entry."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    canonical = Chem.MolToSmiles(mol)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM drugs WHERE smiles = ?", (canonical,)
        ).fetchone()
    return row["name"] if row else None


def build_identity(smiles: str) -> CompoundIdentity:
    mol = parse_smiles_or_raise(smiles)
    canonical = Chem.MolToSmiles(mol)
    return CompoundIdentity(
        smiles=smiles,
        canonical_smiles=canonical,
        canonical_name=lookup_name(smiles),
        molecular_formula=Chem.rdMolDescriptors.CalcMolFormula(mol),
    )


# ---------------------------------------------------------------------------
# Server instance.
# ---------------------------------------------------------------------------
mcp = FastMCP("admet-oracle")


# ===========================================================================
# TOOL 1 (PRE-BUILT): compute_toxicity_alerts
# ---------------------------------------------------------------------------
# Use this as a reference pattern when you implement compute_absorption_profile.
# Notice three things:
#   1. The docstring is what the LLM sees. Make it precise and actionable.
#   2. Every output field carries a confidence level.
#   3. Errors are raised with a structured message, not a generic exception.
# ===========================================================================
@mcp.tool()
def compute_toxicity_alerts(smiles: str) -> ToxicityProfile:
    """Scan a compound for toxicity liabilities.

    Runs three filters: PAINS (assay interference patterns from Baell &
    Holloway 2010), Brenk (unwanted reactive groups from Brenk et al.
    2008), and a hERG cardiac liability heuristic (basic amine plus
    high lipophilicity). All alerts are substructure or rule based and
    should be treated as flags for further investigation, not
    disqualifying evidence.

    Args:
        smiles: SMILES string of the compound to evaluate.

    Returns:
        A ToxicityProfile with the list of alerts and an overall verdict.
    """
    smiles = validate_smiles_input(smiles)
    log.info(f"tool=compute_toxicity_alerts smiles={smiles!r}")

    identity = build_identity(smiles)
    mol = parse_smiles_or_raise(smiles)
    alerts: list[ToxicityAlert] = []

    # PAINS
    for entry in PAINS_CATALOG.GetMatches(mol):
        alerts.append(
            ToxicityAlert(
                name=entry.GetDescription(),
                category="PAINS",
                description="Pan-assay interference pattern; may give "
                "false positives in screening assays.",
                confidence="rule_based",
            )
        )

    # Brenk
    for entry in BRENK_CATALOG.GetMatches(mol):
        alerts.append(
            ToxicityAlert(
                name=entry.GetDescription(),
                category="Brenk",
                description="Reactive, unstable, or otherwise undesirable "
                "moiety per Brenk et al. 2008.",
                confidence="rule_based",
            )
        )

    # hERG heuristic: basic aliphatic N + logP > 3.7 is a coarse risk indicator.
    logp = Descriptors.MolLogP(mol)
    basic_amine_pattern = Chem.MolFromSmarts(
        "[NX3;!$(NC=O);!$(N=*);!$(N#*);!$([n])]"
    )
    has_basic_n = mol.HasSubstructMatch(basic_amine_pattern)
    if has_basic_n and logp > 3.7:
        alerts.append(
            ToxicityAlert(
                name="basic_amine_high_logp",
                category="hERG_heuristic",
                description=f"Basic amine plus logP={logp:.2f}. Coarse "
                "indicator of potential hERG channel binding.",
                confidence="heuristic",
            )
        )

    if not alerts:
        verdict = "clean"
        interp = "No PAINS, Brenk, or hERG heuristic alerts triggered."
    elif len(alerts) <= 2 and all(a.confidence == "heuristic" for a in alerts):
        verdict = "watch"
        interp = "Heuristic flags only; consider follow-up assays."
    else:
        verdict = "concern"
        interp = (
            f"{len(alerts)} alerts including substructure-based liabilities. "
            "Review each before progressing the compound."
        )

    return ToxicityProfile(
        compound=identity,
        alerts=alerts,
        overall_verdict=verdict,
        interpretation=interp,
        sources=[
            "Baell & Holloway 2010 (PAINS)",
            "Brenk et al. 2008 (unwanted moieties)",
            "hERG heuristic: basic amine + logP > 3.7",
        ],
    )


# ===========================================================================
# TOOL 2 (STUB): compute_absorption_profile
# ---------------------------------------------------------------------------
# Implement this in Phase 2. Specification:
#
#   Input:  smiles (str)
#
#   Behaviour:
#       1. Parse the SMILES (use parse_smiles_or_raise).
#       2. Compute these descriptors via RDKit:
#            - molecular weight (Descriptors.MolWt)
#            - logP (Descriptors.MolLogP)
#            - topological polar surface area (Descriptors.TPSA)
#            - hydrogen bond donors (Descriptors.NumHDonors)
#            - hydrogen bond acceptors (Descriptors.NumHAcceptors)
#            - rotatable bonds (Descriptors.NumRotatableBonds)
#       3. Apply three rule sets:
#            Lipinski Rule of Five
#                MW <= 500, logP <= 5, HBD <= 5, HBA <= 10
#            Veber
#                rotatable bonds <= 10, TPSA <= 140
#            Egan
#                logP <= 5.88, TPSA <= 131.6
#       4. For each rule, return pass/fail and the violations list.
#       5. Compute an overall verdict:
#            "favorable"  if all three rules pass
#            "borderline" if exactly one rule fails
#            "poor"       if two or more fail
#       6. Confidence: "experimental" for descriptors, "rule_based" for
#          rules, "heuristic" for the overall verdict.
#
#   Output:
#       Define a Pydantic model AbsorptionProfile that mirrors the shape of
#       ToxicityProfile (compound identity, per-rule results, verdict,
#       interpretation, sources).
#
#   Acceptance test: passing aspirin SMILES returns verdict="favorable".
# ===========================================================================
@mcp.tool()
def compute_absorption_profile(smiles: str) -> AbsorptionProfile:
    """Score a compound's likely oral absorption from physchem descriptors.

    Computes six RDKit descriptors (MW, logP, TPSA, HBD, HBA, rotatable
    bonds) and applies three published rule sets used as first-pass
    oral-bioavailability filters: Lipinski's Rule of Five (MW/logP/HBD/HBA),
    Veber (rotatable bonds, TPSA), and Egan (logP, TPSA). Each rule
    returns pass/fail and a list of which thresholds were violated. The
    overall verdict is heuristic: "favorable" if all three rules pass,
    "borderline" if exactly one fails, "poor" if two or more fail.

    Use this tool to triage candidates for oral dosing or to compare
    bioavailability across analogues. Rule failures are flags, not
    disqualifications — many approved oral drugs (e.g. macrolides)
    violate one or more rules.

    Args:
        smiles: SMILES string of the compound to evaluate.

    Returns:
        An AbsorptionProfile with descriptors, per-rule results, and an
        overall verdict. Confidence levels: descriptors are
        "experimental" (deterministic RDKit), rule results are
        "rule_based", the overall verdict is "heuristic".
    """
    smiles = validate_smiles_input(smiles)
    log.info(f"tool=compute_absorption_profile smiles={smiles!r}")
    started = time.perf_counter()

    identity = build_identity(smiles)
    mol = parse_smiles_or_raise(smiles)

    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    rotb = Descriptors.NumRotatableBonds(mol)

    descriptors = {
        "molecular_weight": Measurement(
            value=round(mw, 2), confidence="experimental",
            source="RDKit Descriptors.MolWt",
        ),
        "logp": Measurement(
            value=round(logp, 2), confidence="experimental",
            source="RDKit Descriptors.MolLogP (Wildman-Crippen)",
        ),
        "tpsa": Measurement(
            value=round(tpsa, 2), confidence="experimental",
            source="RDKit Descriptors.TPSA",
        ),
        "h_bond_donors": Measurement(
            value=hbd, confidence="experimental",
            source="RDKit Descriptors.NumHDonors",
        ),
        "h_bond_acceptors": Measurement(
            value=hba, confidence="experimental",
            source="RDKit Descriptors.NumHAcceptors",
        ),
        "rotatable_bonds": Measurement(
            value=rotb, confidence="experimental",
            source="RDKit Descriptors.NumRotatableBonds",
        ),
    }

    lipinski_violations: list[str] = []
    if mw > 500:
        lipinski_violations.append(f"MW={mw:.1f} > 500")
    if logp > 5:
        lipinski_violations.append(f"logP={logp:.2f} > 5")
    if hbd > 5:
        lipinski_violations.append(f"HBD={hbd} > 5")
    if hba > 10:
        lipinski_violations.append(f"HBA={hba} > 10")

    veber_violations: list[str] = []
    if rotb > 10:
        veber_violations.append(f"rotatable_bonds={rotb} > 10")
    if tpsa > 140:
        veber_violations.append(f"TPSA={tpsa:.1f} > 140")

    egan_violations: list[str] = []
    if logp > 5.88:
        egan_violations.append(f"logP={logp:.2f} > 5.88")
    if tpsa > 131.6:
        egan_violations.append(f"TPSA={tpsa:.1f} > 131.6")

    rules = [
        RuleResult(
            name="Lipinski",
            **{"pass": not lipinski_violations},
            violations=lipinski_violations,
            confidence="rule_based",
        ),
        RuleResult(
            name="Veber",
            **{"pass": not veber_violations},
            violations=veber_violations,
            confidence="rule_based",
        ),
        RuleResult(
            name="Egan",
            **{"pass": not egan_violations},
            violations=egan_violations,
            confidence="rule_based",
        ),
    ]

    failed = sum(1 for r in rules if not r.pass_)
    if failed == 0:
        verdict = "favorable"
        interp = (
            "All three rule sets (Lipinski, Veber, Egan) pass. "
            "Physchem profile is consistent with reasonable oral absorption."
        )
    elif failed == 1:
        verdict = "borderline"
        failing = next(r.name for r in rules if not r.pass_)
        interp = (
            f"One rule set fails ({failing}). Oral absorption may be "
            "compromised but is not ruled out; many approved drugs violate "
            "one rule. Review the violation details."
        )
    else:
        verdict = "poor"
        failing = ", ".join(r.name for r in rules if not r.pass_)
        interp = (
            f"{failed} rule sets fail ({failing}). Oral absorption is "
            "unlikely without formulation work or a structural redesign."
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info(
        f"tool=compute_absorption_profile "
        f"compound={identity.canonical_name or 'unknown'} "
        f"verdict={verdict} elapsed_ms={elapsed_ms:.1f}"
    )

    return AbsorptionProfile(
        compound=identity,
        descriptors=descriptors,
        rules=rules,
        overall_verdict=verdict,
        interpretation=interp,
        sources=[
            "Lipinski et al. 1997 (Rule of Five)",
            "Veber et al. 2002 (rotatable bonds, TPSA)",
            "Egan et al. 2000 (logP, TPSA)",
        ],
    )


# ===========================================================================
# RESOURCE 1 (PRE-BUILT): reference://{name}
# ===========================================================================
@mcp.resource("reference://{name}")
def reference_compound(name: str) -> str:
    """Return canonical SMILES and identifying info for a named drug.

    Use names like 'aspirin', 'imatinib', 'fluoxetine'. Lookup is
    case-insensitive. This resource lets the LLM ground its analysis on
    real compounds without inventing SMILES strings.
    """
    log.info(f"resource=reference name={name!r}")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM drugs WHERE name_lower = ?", (name.lower(),)
        ).fetchone()
    if row is None:
        return json.dumps(
            {"error": f"No reference compound named '{name}' in library."}
        )
    return json.dumps(
        {
            "drug_id": row["drug_id"],
            "name": row["name"],
            "smiles": row["smiles"],
            "inchi_key": row["inchi_key"],
            "therapeutic_class": row["therapeutic_class"],
            "route_of_admin": row["route_of_admin"],
            "approval_year": row["approval_year"],
            "known_admet_flags": json.loads(row["known_admet_flags"]),
        },
        indent=2,
    )


# ===========================================================================
# RESOURCE 2: compound://{drug_id}
# ===========================================================================
@mcp.resource("compound://{drug_id}")
def compound_record(drug_id: str) -> str:
    """Return library record for a compound looked up by DrugBank-style id.

    Use ids like 'DB00945' (aspirin). On miss the response is a JSON
    object with an 'error' field rather than an exception, so the host
    can keep going.
    """
    log.info(f"resource=compound drug_id={drug_id!r}")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM drugs WHERE drug_id = ?", (drug_id,)
        ).fetchone()
    if row is None:
        return json.dumps(
            {"error": f"No compound with drug_id '{drug_id}' in library."}
        )
    return json.dumps(
        {
            "drug_id": row["drug_id"],
            "name": row["name"],
            "smiles": row["smiles"],
            "inchi_key": row["inchi_key"],
            "therapeutic_class": row["therapeutic_class"],
            "route_of_admin": row["route_of_admin"],
            "approval_year": row["approval_year"],
            "known_admet_flags": json.loads(row["known_admet_flags"]),
        },
        indent=2,
    )


# ===========================================================================
# PROMPT: admet_triage
# ===========================================================================
@mcp.prompt()
def admet_triage(
    compound_identifier: str,
    therapeutic_context: str,
    concerns: str,
) -> str:
    """Standard ADMET triage protocol for a compound under a therapeutic context.

    Parameterized institutional knowledge: any host connecting to this
    server gets the same triage discipline without copy-pasting prompt
    text.
    """
    return f"""You are performing an ADMET triage on **{compound_identifier}** for the following therapeutic context:

    {therapeutic_context}

The user is specifically concerned about:

    {concerns}

Follow this protocol exactly:

1. **Resolve the compound.** First try the `reference://{{name}}` resource
   with the lowercase compound name. If that misses, try
   `compound://{{drug_id}}` if a DrugBank-style id is available. Capture
   the canonical SMILES from the resource — do not invent one.

2. **Run both ADMET tools on that SMILES.** Call
   `compute_absorption_profile` and `compute_toxicity_alerts`. Do not
   skip either, even if one looks redundant for the stated concern.

3. **Synthesize the verdict with explicit confidence tagging.** When you
   report a finding, label each piece of evidence as one of:
   - *experimental* — deterministic descriptor values (trust as
     measurements, not as predictions of in-vivo behaviour)
   - *rule_based* — pass/fail under a published rule set
     (Lipinski/Veber/Egan, PAINS, Brenk)
   - *heuristic* — coarse indicators like the hERG basic-amine flag or
     the overall absorption verdict
   Treat heuristic flags as triggers for follow-up assays, not as
   disqualifications. Many approved drugs fail one or more rule sets.

4. **Close with a medicinal-chemist recommendation** that ties the
   findings back to *{therapeutic_context}* and addresses *{concerns}*
   directly. Be specific about what would change your assessment (e.g.
   "an in-vitro hERG IC50 above 10 µM would downgrade this flag"). If
   the data is insufficient, say so plainly rather than padding.

Output format: a brief findings table followed by a single
recommendation paragraph. Keep it terse — assume the reader is a
senior medicinal chemist.
"""


# ---------------------------------------------------------------------------
# Entry point. Transport selection happens via env var so we do not have
# to edit the file when switching from stdio to streamable HTTP in Phase 5.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        log.info("Starting on streamable-http transport at port 8000")
        mcp.run(transport="streamable-http")
    else:
        log.info("Starting on stdio transport")
        mcp.run(transport="stdio")
