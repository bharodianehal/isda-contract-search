"""FINOS CDM (Common Domain Model) alignment for extracted ISDA/CSA clauses.

Pure functions (no Streamlit) so they are unit-testable. Maps the AI-extracted
clause register + structured eligible collateral onto a CDM-aligned
`LegalAgreement`, and validates the result with jsonschema against a schema
describing the representation this app produces (types, Party1/Party2 roles,
typed {value,currency} amounts, eligible-collateral rule sets).

This is NOT the full FINOS release schema — binding to that needs the CDM
distribution artifacts (Rosetta-generated). Values map to the same CDM types
ISDA Create digitizes CSAs into.
"""
import re

# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH: the clause schema is DERIVED FROM THE CDM legal-
# agreement model. Each entry names the clause, the CDM path it populates, and
# the extraction guidance. The extractor (deploy/07) builds its LLM prompt from
# this, build_cdm() maps values by these names, and the UI mapping panel reads
# CDM_MAP from it — so extraction and CDM digitization share one definition.
# Adding/removing a clause = editing this list only.
# ---------------------------------------------------------------------------
CLAUSE_SCHEMA = [
    {"name": "Party A", "cdm": "contractualParty[Party1].partyName",
     "guidance": "The first party (Party A)."},
    {"name": "Counterparty (Party B)",
     "cdm": "contractualParty[Party2].partyName",
     "guidance": "The counterparty / Party B legal entity name."},
    {"name": "Counterparty LEI", "cdm": "contractualParty[Party2].partyId[LEI]",
     "guidance": "Party B's Legal Entity Identifier (20 chars)."},
    {"name": "Governing Law", "cdm": "legalAgreementIdentification.governingLaw",
     "guidance": "Governing law of the agreement (e.g., New York, English)."},
    {"name": "Effective Date", "cdm": "legalAgreement.effectiveDate",
     "guidance": "The 'dated as of' effective date."},
    {"name": "Base Currency",
     "cdm": "creditSupportAgreementElections.baseAndEligibleCurrency.baseCurrency",
     "guidance": "CSA Base Currency."},
    {"name": "Eligible Collateral",
     "cdm": "creditSupportAgreementElections.eligibleCollateral[]",
     "guidance": "Types of eligible collateral accepted."},
    {"name": "Threshold",
     "cdm": "creditSupportAgreementElections.threshold.partyElection[]",
     "guidance": "CSA Threshold amount for Party B (currency amount)."},
    {"name": "Minimum Transfer Amount",
     "cdm": "creditSupportAgreementElections.minimumTransferAmount.partyElection[]",
     "guidance": "CSA Minimum Transfer Amount."},
    {"name": "Independent Amount",
     "cdm": "creditSupportAgreementElections.independentAmount.partyElection[]",
     "guidance": "CSA Independent Amount for Party B."},
    {"name": "Automatic Early Termination",
     "cdm": "masterAgreementElections.automaticEarlyTermination",
     "guidance": "Whether Automatic Early Termination applies (Yes/No and to whom)."},
    {"name": "Cross-Default Threshold Amount",
     "cdm": "masterAgreementElections.crossDefault.thresholdAmount",
     "guidance": "The Threshold Amount for the Cross-Default provision."},
    {"name": "Specified Entity",
     "cdm": "masterAgreementElections.specifiedEntity",
     "guidance": "The Specified Entity in relation to Party B."},
    {"name": "Additional Termination Events",
     "cdm": "masterAgreementElections.additionalTerminationEvent[]",
     "guidance": "Any Additional Termination Events listed."},
    {"name": "Valuation Agent",
     "cdm": "creditSupportAgreementElections.valuationAndTiming.valuationAgent",
     "guidance": "The Valuation/Calculation Agent."},
    {"name": "Interest Rate on Cash Collateral",
     "cdm": "creditSupportAgreementElections.interestRate",
     "guidance": "The interest rate/reference on cash collateral "
                 "(e.g., SOFR/EURSTR/SONIA)."},
    {"name": "Set-off", "cdm": "masterAgreementElections.setOff",
     "guidance": "Whether a Set-off provision applies."},
    {"name": "Bail-in Recognition",
     "cdm": "masterAgreementElections.contractualRecognitionOfBailin",
     "guidance": "Whether contractual recognition of bail-in (BRRD Article 55) "
                 "is present."},
]

# Derived views of the single source of truth.
CDM_MAP = [(c["name"], c["cdm"]) for c in CLAUSE_SCHEMA]
EXTRACTION_CLAUSES = [(c["name"], c["guidance"], c["cdm"]) for c in CLAUSE_SCHEMA]

_CCY = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", None]


def _parse_amount(s):
    """'EUR 20,000,000' -> {'value':20000000.0,'currency':'EUR'}; None if none."""
    s = str(s or "")
    num = re.search(r"([\d][\d,]*(?:\.\d+)?)", s)
    if not num:
        return None
    try:
        val = float(num.group(1).replace(",", ""))
    except ValueError:
        return None
    cur = re.search(r"\b(USD|EUR|GBP|CHF|JPY|CAD|AUD)\b", s)
    return {"value": val, "currency": cur.group(1) if cur else None}


def _party_amount(by, clause, party="Party2"):
    r = by.get(clause)
    if not r or not str(r.get("value", "")).strip():
        return None
    amt = _parse_amount(r["value"])
    if amt:
        return {"partyElection": [{"party": party, "amount": amt}]}
    return {"partyElection": [{"party": party, "value": r["value"]}]}


def _eligible_collateral(doc_id, collateral_rows):
    out = []
    for c in collateral_rows or []:
        if c.get("doc_id") != doc_id:
            continue

        def _num(x):
            try:
                return float(x) if x not in (None, "") else None
            except (TypeError, ValueError):
                return None
        out.append({
            "assetType": c.get("asset_type"),
            "issuer": c.get("issuer") or None,
            "maturityBand": c.get("maturity_band") or None,
            "currency": c.get("currency") or None,
            "treatment": {
                "valuationPercentage": _num(c.get("valuation_percentage")),
                "haircutPercentage": _num(c.get("haircut_percentage"))},
        })
    return out


def build_cdm(doc_id, ex_rows, collateral_rows=None, model=""):
    """Map the extracted clause register onto a CDM-aligned LegalAgreement."""
    by = {r["clause_name"]: r for r in ex_rows}

    def v(c):
        return by.get(c, {}).get("value")

    aet = str(v("Automatic Early Termination") or "").lower()
    p2_aet = ("appl" in aet and not aet.strip().startswith("not")
              and "not apply to either" not in aet)
    ate = [x.strip() for x in re.split(r"[;\n]",
           str(v("Additional Termination Events") or "")) if x.strip()]
    return {
        "legalAgreement": {
            "agreementDate": v("Effective Date"),
            "effectiveDate": v("Effective Date"),
            "legalAgreementIdentification": {
                "agreementType": "CreditSupportAgreement",
                "governingLaw": v("Governing Law"),
            },
            "contractualParty": [
                {"role": "Party1", "partyName": v("Party A")},
                {"role": "Party2", "partyName": v("Counterparty (Party B)"),
                 "partyId": [{"identifier": v("Counterparty LEI"),
                              "identifierType": "LEI"}]},
            ],
            "agreementTerms": {"agreement": {
                "creditSupportAgreementElections": {
                    "baseAndEligibleCurrency": {
                        "baseCurrency": v("Base Currency")},
                    "threshold": _party_amount(by, "Threshold"),
                    "minimumTransferAmount": _party_amount(
                        by, "Minimum Transfer Amount"),
                    "independentAmount": _party_amount(by, "Independent Amount"),
                    "eligibleCollateral": (
                        _eligible_collateral(doc_id, collateral_rows)
                        or [{"description": v("Eligible Collateral")}]),
                    "valuationAndTiming": {"valuationAgent": v("Valuation Agent")},
                    "interestRate": v("Interest Rate on Cash Collateral"),
                },
                "masterAgreementElections": {
                    "governingLaw": v("Governing Law"),
                    "automaticEarlyTermination": {"Party1": False, "Party2": p2_aet},
                    "crossDefault": {
                        "applicable": True,
                        "thresholdAmount": _parse_amount(
                            v("Cross-Default Threshold Amount"))},
                    "specifiedEntity": {"Party2": v("Specified Entity")},
                    "additionalTerminationEvent": ate,
                    "setOff": {"applicable":
                               "yes" in str(v("Set-off") or "").lower()},
                    "contractualRecognitionOfBailin": {
                        "applicable":
                        "yes" in str(v("Bail-in Recognition") or "").lower()},
                },
            }},
        },
        "meta": {
            "cdmAligned": True,
            "cdmReference": ("FINOS CDM: LegalAgreement / "
                             "CreditSupportAgreementElections / "
                             "MasterAgreementElections"),
            "extractedBy": model,
            "provenance": {r["clause_name"]: {
                "page": r["page"], "confidence": float(r["confidence"] or 0),
                "snippet": r["snippet"]} for r in ex_rows},
        },
    }


CDM_ALIGNED_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["legalAgreement", "meta"],
    "$defs": {
        "amount": {
            "type": "object", "required": ["value"],
            "properties": {"value": {"type": "number"},
                           "currency": {"enum": _CCY}},
        },
        "partyAmount": {
            "type": ["object", "null"],
            "properties": {"partyElection": {
                "type": "array", "items": {
                    "type": "object", "required": ["party"],
                    "properties": {
                        "party": {"enum": ["Party1", "Party2"]},
                        "amount": {"$ref": "#/$defs/amount"},
                        "value": {"type": "string"}}}}},
        },
    },
    "properties": {
        "legalAgreement": {
            "type": "object",
            "required": ["contractualParty", "legalAgreementIdentification",
                         "agreementTerms"],
            "properties": {
                "effectiveDate": {"type": ["string", "null"]},
                "legalAgreementIdentification": {
                    "type": "object", "required": ["governingLaw"],
                    "properties": {"agreementType": {"type": "string"},
                                   "governingLaw": {"type": "string"}}},
                "contractualParty": {
                    "type": "array", "minItems": 2, "maxItems": 2,
                    "items": {"type": "object", "required": ["role", "partyName"],
                              "properties": {
                                  "role": {"enum": ["Party1", "Party2"]},
                                  "partyName": {"type": "string"}}}},
                "agreementTerms": {
                    "type": "object", "required": ["agreement"],
                    "properties": {"agreement": {
                        "type": "object",
                        "required": ["creditSupportAgreementElections",
                                     "masterAgreementElections"],
                        "properties": {
                            "creditSupportAgreementElections": {
                                "type": "object",
                                "required": ["baseAndEligibleCurrency",
                                             "eligibleCollateral"],
                                "properties": {
                                    "baseAndEligibleCurrency": {
                                        "type": "object",
                                        "required": ["baseCurrency"],
                                        "properties": {"baseCurrency": {
                                            "type": "string"}}},
                                    "threshold": {"$ref": "#/$defs/partyAmount"},
                                    "minimumTransferAmount": {
                                        "$ref": "#/$defs/partyAmount"},
                                    "independentAmount": {
                                        "$ref": "#/$defs/partyAmount"},
                                    "eligibleCollateral": {
                                        "type": "array", "minItems": 1}}},
                            "masterAgreementElections": {
                                "type": "object",
                                "required": ["automaticEarlyTermination",
                                             "crossDefault"],
                                "properties": {
                                    "automaticEarlyTermination": {
                                        "type": "object",
                                        "properties": {
                                            "Party1": {"type": "boolean"},
                                            "Party2": {"type": "boolean"}}},
                                    "crossDefault": {"type": "object"}}}}}}},
            },
        },
        "meta": {"type": "object", "required": ["cdmAligned"],
                 "properties": {"cdmAligned": {"const": True}}},
    },
}


def validate_cdm(doc):
    """Validate against CDM_ALIGNED_SCHEMA. Returns (ok, [error strings])."""
    import jsonschema
    validator = jsonschema.Draft202012Validator(CDM_ALIGNED_SCHEMA)
    errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    return (not errs), ["%s: %s" % ("/".join(str(p) for p in e.path) or "(root)",
                                    e.message) for e in errs[:12]]
