"""Step 7 (P1/P2/P6): AI clause extraction into a structured clause register.

For each agreement, a Foundation Model (databricks-claude-sonnet-4-6) reads the
page-annotated text and extracts the negotiated ISDA/CSA clauses into structured
rows, each with value + source page + verbatim snippet + confidence — the
pattern from the ISDA May-2025 GenAI paper, generalized beyond the 5 CSA clauses.

Writes table `clause_extractions` (+ HITL review columns). Accuracy-vs-golden
(P2) is computed in the app by comparing to the structured columns already in
`documents` (our ground truth).
"""
import json
import os
import re
import sys

# The clause schema is the single source of truth, DERIVED FROM THE CDM legal-
# agreement model (app/cdm.py). The extraction prompt is generated from it, so
# extraction and CDM digitization stay in lock-step.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import cdm  # noqa: E402

import dbx  # noqa: E402

MODEL = dbx.LLM_MODEL  # from config.env

SCHEMA_HINT = ('Return ONLY a JSON array. Each element: '
               '{"clause_name": string, "value": string, "page": integer, '
               '"snippet": string (<=200 chars, verbatim), '
               '"confidence": number 0.0-1.0}. '
               'If a clause is not present, set value to "Not specified", '
               'page to 0, and a low confidence.')


def annotated_text(w, r, doc_id):
    rows = dbx.run_sql(w, "SELECT page, chunk_text FROM %s WHERE doc_id='%s' "
                       "ORDER BY page" % (r["chunks_table"], doc_id))
    return "\n\n".join("[PAGE %s] %s" % (x["page"], x["chunk_text"]) for x in rows)


def build_prompt(text):
    # Prompt lines are generated from the CDM-derived schema, and each names the
    # CDM element it maps to (the domain-context lever from the ISDA GenAI paper).
    lines = "\n".join("- %s (CDM: %s): %s" % (n, cdm_path, g)
                      for n, g, cdm_path in cdm.EXTRACTION_CLAUSES)
    return ("You are an expert ISDA and CSA contract analyst. From the agreement "
            "text below (pages are marked [PAGE n]), extract these data points "
            "(defined by the FINOS Common Domain Model legal-agreement schema), "
            "using the exact wording of the contract for values.\n\nDATA POINTS:\n"
            + lines + "\n\n" + SCHEMA_HINT +
            "\n\n=== AGREEMENT TEXT ===\n" + text)


def extract_one(w, r, doc_id):
    prompt = build_prompt(annotated_text(w, r, doc_id)).replace("'", "''")
    rows = dbx.run_sql(w, "SELECT ai_query('%s', '%s') AS out" % (MODEL, prompt))
    raw = rows[0]["out"]
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    data = json.loads(m.group(0) if m else raw)
    return data


def ensure_table(w, r):
    dbx.run_sql(w, """
    CREATE TABLE IF NOT EXISTS {tbl} (
        doc_id STRING, clause_name STRING, value STRING, page INT,
        snippet STRING, confidence DOUBLE, model STRING, extracted_at TIMESTAMP,
        status STRING, reviewed_value STRING, reviewed_by STRING,
        reviewed_at TIMESTAMP
    ) TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """.format(tbl=r["extractions_table"]))


def insert_rows(w, r, doc_id, data):
    vals = []
    for d in data:
        cn = str(d.get("clause_name", "")).replace("'", "''")[:120]
        v = str(d.get("value", "")).replace("'", "''")[:1000]
        sn = str(d.get("snippet", "")).replace("'", "''")[:500]
        try:
            pg = int(d.get("page", 0) or 0)
        except Exception:
            pg = 0
        try:
            cf = float(d.get("confidence", 0) or 0)
        except Exception:
            cf = 0.0
        vals.append("('%s','%s','%s',%d,'%s',%f,'%s',current_timestamp(),"
                    "'pending',NULL,NULL,NULL)"
                    % (doc_id, cn, v, pg, sn, cf, MODEL))
    if vals:
        dbx.run_sql(w, "INSERT INTO %s VALUES %s" % (r["extractions_table"],
                                                     ",".join(vals)))


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    r["extractions_table"] = "%s.%s.clause_extractions" % (r["catalog"], r["schema"])
    dbx.save_resolved(r)

    ensure_table(w, r)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    docs = dbx.run_sql(w, "SELECT doc_id FROM %s ORDER BY doc_id"
                       % r["documents_table"])
    doc_ids = [d["doc_id"] for d in docs]
    if only:
        doc_ids = [only]
    else:
        dbx.run_sql(w, "DELETE FROM %s" % r["extractions_table"])  # full refresh

    total = 0
    for did in doc_ids:
        try:
            data = extract_one(w, r, did)
            insert_rows(w, r, did, data)
            total += len(data)
            print("extracted %-6s -> %d clauses" % (did, len(data)))
        except Exception as e:
            print("FAILED %s: %s" % (did, str(e)[:200]))
    print("\nDONE: %d clause rows in %s" % (total, r["extractions_table"]))
    # app-SP grants happen in 05_deploy_app.py


if __name__ == "__main__":
    main()
