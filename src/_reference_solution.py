"""
Reference solutions for the lab stubs.

Do NOT distribute this file to students. Use it during the lab only to:
  - sanity-check student work
  - help unblock students who are stuck for more than ~5 minutes
  - run end-to-end during dry runs

The complete solution covers Phase 2 (absorption tool), Phase 3 (compound
resource), and Phase 4 (admet_triage prompt).
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from rdkit.Chem import Descriptors

from starter_server import (
    CompoundIdentity,
    ConfidenceLevel,
    Measurement,
    build_identity,
    get_conn,
    parse_smiles_or_raise,
)

log = logging.getLogger("admet")


# ---------------------------------------------------------------------------
# Phase 2 reference: AbsorptionProfile + compute_absorption_profile
# ---------------------------------------------------------------------------
class RuleResult(BaseModel):
    rule: str
    pass_: bool
    violations: list[str]
    confidence: ConfidenceLevel


class AbsorptionProfile(BaseModel):
    compound: CompoundIdentity
    descriptors: dict[str, Measurement]
    rules: list[RuleResult]
    overall_verdict: Literal["favorable", "borderline", "poor"]
    overall_confidence: ConfidenceLevel
    interpretation: str
    sources: list[str]


def evaluate_absorption(smiles: str) -> AbsorptionProfile:
    """Reference implementation. Wire to @mcp.tool() in the live demo."""
    log.info(f"tool=compute_absorption_profile smiles={smiles!r}")

    identity = build_identity(smiles)
    mol = parse_smiles_or_raise(smiles)

    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    rotb = Descriptors.NumRotatableBonds(mol)

    descriptors = {
        "mw": Measurement(value=round(mw, 2), confidence="experimental",
                          source="RDKit Descriptors.MolWt"),
        "logp": Measurement(value=round(logp, 2), confidence="experimental",
                            source="RDKit Crippen logP"),
        "tpsa": Measurement(value=round(tpsa, 2), confidence="experimental",
                            source="RDKit Descriptors.TPSA"),
        "hbd": Measurement(value=hbd, confidence="experimental",
                           source="RDKit Descriptors.NumHDonors"),
        "hba": Measurement(value=hba, confidence="experimental",
                           source="RDKit Descriptors.NumHAcceptors"),
        "rotatable_bonds": Measurement(value=rotb, confidence="experimental",
                                       source="RDKit Descriptors.NumRotatableBonds"),
    }

    # Lipinski Rule of Five
    lipinski_violations = []
    if mw > 500: lipinski_violations.append(f"MW={mw:.1f} > 500")
    if logp > 5: lipinski_violations.append(f"logP={logp:.2f} > 5")
    if hbd > 5: lipinski_violations.append(f"HBD={hbd} > 5")
    if hba > 10: lipinski_violations.append(f"HBA={hba} > 10")

    # Veber
    veber_violations = []
    if rotb > 10: veber_violations.append(f"rotatable_bonds={rotb} > 10")
    if tpsa > 140: veber_violations.append(f"TPSA={tpsa:.1f} > 140")

    # Egan
    egan_violations = []
    if logp > 5.88: egan_violations.append(f"logP={logp:.2f} > 5.88")
    if tpsa > 131.6: egan_violations.append(f"TPSA={tpsa:.1f} > 131.6")

    rules = [
        RuleResult(rule="lipinski", pass_=not lipinski_violations,
                   violations=lipinski_violations, confidence="rule_based"),
        RuleResult(rule="veber", pass_=not veber_violations,
                   violations=veber_violations, confidence="rule_based"),
        RuleResult(rule="egan", pass_=not egan_violations,
                   violations=egan_violations, confidence="rule_based"),
    ]

    failures = sum(1 for r in rules if not r.pass_)
    if failures == 0:
        verdict, interp = "favorable", "All three rule sets pass."
    elif failures == 1:
        failed = next(r.rule for r in rules if not r.pass_)
        verdict, interp = "borderline", f"Single rule failed ({failed})."
    else:
        verdict, interp = "poor", f"{failures} of 3 rule sets failed."

    return AbsorptionProfile(
        compound=identity,
        descriptors=descriptors,
        rules=rules,
        overall_verdict=verdict,
        overall_confidence="heuristic",
        interpretation=interp,
        sources=[
            "Lipinski et al. 1997 (Rule of Five)",
            "Veber et al. 2002 (oral bioavailability)",
            "Egan et al. 2000 (passive absorption)",
        ],
    )


def register(mcp: FastMCP) -> None:
    """Wire all reference solutions onto a FastMCP instance."""

    @mcp.tool()
    def compute_absorption_profile(smiles: str) -> AbsorptionProfile:
        """Evaluate oral absorption potential via Lipinski, Veber, and Egan
        rules. Returns descriptor values, per-rule pass/fail, and an overall
        verdict. Confidence: descriptors are experimental (deterministic
        RDKit calculations); rule verdicts are rule_based; the overall
        verdict is heuristic."""
        return evaluate_absorption(smiles)

    @mcp.resource("compound://{drug_id}")
    def compound_record(drug_id: str) -> str:
        """Look up a compound by DrugBank-style ID."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM drugs WHERE drug_id = ?", (drug_id,)
            ).fetchone()
        if row is None:
            return json.dumps({"error": f"No compound with id '{drug_id}'."})
        return json.dumps({k: row[k] for k in row.keys()}, indent=2)

    @mcp.prompt()
    def admet_triage(
        compound_identifier: str,
        therapeutic_context: str,
        concerns: str,
    ) -> str:
        """Generate a triage instruction for a compound."""
        return (
            f"Evaluate the ADMET profile of {compound_identifier} for use in "
            f"{therapeutic_context}. Pay particular attention to {concerns}.\n\n"
            "Use these steps:\n"
            "1. Resolve the compound via the reference:// or compound:// "
            "resource to get a validated SMILES.\n"
            "2. Call compute_absorption_profile and compute_toxicity_alerts.\n"
            "3. Synthesize a verdict that explicitly distinguishes between "
            "experimental measurements, rule_based determinations, and "
            "heuristic flags. Treat heuristic flags as 'investigate further' "
            "rather than disqualifying.\n"
            "4. Produce a recommendation in medicinal chemist language."
        )
