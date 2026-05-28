"""
Build the ADMET library SQLite database from a curated list of FDA-approved
drugs. SMILES strings are public information sourced from DrugBank and
PubChem. The selection is deliberate: it covers multiple therapeutic classes,
includes BBB penetrants and non-penetrants, and contains compounds with
documented ADMET liabilities so the toxicity tools light up on familiar
names.

Run once before the lab:
    python data/seed_db.py
"""

import json
import sqlite3
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import inchi

DB_PATH = Path(__file__).parent / "admet_library.db"

# Curated set: ~35 well-known FDA approved drugs.
# Format: (drug_id, name, smiles, therapeutic_class, route, year, flags)
DRUGS = [
    # NSAIDs and analgesics
    ("DB00945", "Aspirin", "CC(=O)Oc1ccccc1C(=O)O", "analgesic", "oral", 1899, []),
    ("DB01050", "Ibuprofen", "CC(C)Cc1ccc(C(C)C(=O)O)cc1", "analgesic", "oral", 1974, []),
    ("DB00788", "Naproxen", "COc1ccc2cc(C(C)C(=O)O)ccc2c1", "analgesic", "oral", 1976, []),
    ("DB00482", "Celecoxib", "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1", "analgesic", "oral", 1998, []),
    ("DB00316", "Acetaminophen", "CC(=O)Nc1ccc(O)cc1", "analgesic", "oral", 1955, ["hepatotoxic_overdose"]),

    # CNS agents
    ("DB00829", "Diazepam", "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21", "CNS", "oral", 1963, ["bbb_penetrant"]),
    ("DB00472", "Fluoxetine", "CNCCC(Oc1ccc(C(F)(F)F)cc1)c1ccccc1", "CNS", "oral", 1987, ["bbb_penetrant"]),
    ("DB01104", "Sertraline", "CNC1CCc2ccc(Cl)c(Cl)c2C1c1ccccc1", "CNS", "oral", 1991, ["bbb_penetrant"]),
    ("DB00215", "Citalopram", "N#Cc1ccc2c(c1)C(c1ccc(F)cc1)(CCCN(C)C)CO2", "CNS", "oral", 1989, ["bbb_penetrant"]),
    ("DB00502", "Haloperidol", "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1", "CNS", "oral", 1967, ["bbb_penetrant", "hERG_risk"]),
    ("DB00734", "Risperidone", "Cc1c(CCN2CCC(c3noc4cc(F)ccc34)CC2)c(=O)n2CCCCc2n1", "CNS", "oral", 1993, ["bbb_penetrant"]),

    # Cardiovascular
    ("DB01076", "Atorvastatin", "CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O", "cardiovascular", "oral", 1996, []),
    ("DB00641", "Simvastatin", "CCC(C)(C)C(=O)OC1CC(C)C=C2C=CC(C)C(CCC3CC(O)CC(=O)O3)C12", "cardiovascular", "oral", 1991, []),
    ("DB00722", "Lisinopril", "NCCCCC(NC(CCc1ccccc1)C(=O)N1CCCC1C(=O)O)C(=O)O", "cardiovascular", "oral", 1987, []),
    ("DB00678", "Losartan", "CCCCc1nc(Cl)c(CO)n1Cc1ccc(-c2ccccc2-c2nnn[nH]2)cc1", "cardiovascular", "oral", 1995, []),
    ("DB00381", "Amlodipine", "CCOC(=O)C1=C(COCCN)NC(C)=C(C(=O)OC)C1c1ccccc1Cl", "cardiovascular", "oral", 1990, []),
    ("DB00682", "Warfarin", "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O", "cardiovascular", "oral", 1954, ["narrow_therapeutic_index"]),
    ("DB00264", "Metoprolol", "COCCc1ccc(OCC(O)CNC(C)C)cc1", "cardiovascular", "oral", 1978, ["bbb_penetrant"]),
    ("DB00571", "Propranolol", "CC(C)NCC(O)COc1cccc2ccccc12", "cardiovascular", "oral", 1967, ["bbb_penetrant"]),

    # Anti-infectives
    ("DB01060", "Amoxicillin", "CC1(C)SC2C(NC(=O)C(N)c3ccc(O)cc3)C(=O)N2C1C(=O)O", "anti-infective", "oral", 1972, []),
    ("DB00537", "Ciprofloxacin", "O=C(O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O", "anti-infective", "oral", 1987, []),
    ("DB00207", "Azithromycin", "CCC1OC(=O)C(C)C(OC2CC(C)(OC)C(O)C(C)O2)C(C)C(OC2OC(C)CC(N(C)C)C2O)C(C)(O)CC(C)CN(C)C(C)C(O)C1(C)O", "anti-infective", "oral", 1991, []),
    ("DB00254", "Doxycycline", "CC1c2cccc(O)c2C(=O)C2=C(O)C3(O)C(=O)C(C(N)=O)=C(O)C(N(C)C)C3C(O)C12", "anti-infective", "oral", 1967, []),
    ("DB00916", "Metronidazole", "Cc1ncc([N+](=O)[O-])n1CCO", "anti-infective", "oral", 1963, []),

    # Oncology
    ("DB00619", "Imatinib", "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1", "oncology", "oral", 2001, []),
    ("DB00317", "Gefitinib", "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1", "oncology", "oral", 2003, []),
    ("DB00530", "Erlotinib", "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1", "oncology", "oral", 2004, []),
    ("DB00675", "Tamoxifen", "CC/C(=C(/c1ccccc1)c1ccc(OCCN(C)C)cc1)c1ccccc1", "oncology", "oral", 1977, []),
    ("DB00563", "Methotrexate", "CN(Cc1cnc2nc(N)nc(N)c2n1)c1ccc(C(=O)NC(CCC(=O)O)C(=O)O)cc1", "oncology", "oral", 1953, []),

    # Metabolic
    ("DB00331", "Metformin", "CN(C)C(=N)NC(=N)N", "metabolic", "oral", 1995, []),
    ("DB01261", "Sitagliptin", "NC(CC(=O)N1CCn2c(nnc2C(F)(F)F)C1)Cc1cc(F)c(F)cc1F", "metabolic", "oral", 2006, []),

    # GI
    ("DB00338", "Omeprazole", "COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1", "GI", "oral", 1989, []),

    # Antihistamines
    ("DB01075", "Diphenhydramine", "CN(C)CCOC(c1ccccc1)c1ccccc1", "antihistamine", "oral", 1946, ["bbb_penetrant"]),
    ("DB00455", "Loratadine", "CCOC(=O)N1CCC(=C2c3ccc(Cl)cc3CCc3cccnc32)CC1", "antihistamine", "oral", 1993, []),

    # Other notable
    ("DB00203", "Sildenafil", "CCCc1nn(C)c2c1nc([nH]c2=O)-c1cc(S(=O)(=O)N2CCN(C)CC2)ccc1OCC", "PDE5", "oral", 1998, []),
    ("DB00201", "Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O", "stimulant", "oral", 1819, ["bbb_penetrant"]),
]


def validate_smiles(smiles: str, name: str) -> str:
    """Canonicalize SMILES and warn if invalid."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES for {name}: {smiles}")
    return Chem.MolToSmiles(mol)


def build_database(db_path: Path = DB_PATH) -> None:
    """Create a fresh database and populate it."""
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE drugs (
            drug_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            name_lower TEXT NOT NULL,
            smiles TEXT NOT NULL,
            inchi_key TEXT NOT NULL,
            therapeutic_class TEXT NOT NULL,
            route_of_admin TEXT NOT NULL,
            approval_year INTEGER,
            known_admet_flags TEXT NOT NULL
        )
        """
    )
    cur.execute("CREATE INDEX idx_drugs_name_lower ON drugs(name_lower)")
    cur.execute("CREATE INDEX idx_drugs_class ON drugs(therapeutic_class)")

    rows = []
    for drug_id, name, smiles, klass, route, year, flags in DRUGS:
        canonical = validate_smiles(smiles, name)
        mol = Chem.MolFromSmiles(canonical)
        ikey = inchi.MolToInchiKey(mol)
        rows.append(
            (
                drug_id,
                name,
                name.lower(),
                canonical,
                ikey,
                klass,
                route,
                year,
                json.dumps(flags),
            )
        )

    cur.executemany(
        "INSERT INTO drugs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()
    conn.close()
    print(f"Built {db_path} with {len(rows)} compounds.")


if __name__ == "__main__":
    build_database()
