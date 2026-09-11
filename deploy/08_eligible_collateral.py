"""Step 8: Extract structured Eligible Collateral rule sets.

CDM models eligible collateral as machine-evaluable rule sets (asset class,
issuer, maturity band, valuation percentage / haircut) — not free text. This
script uses ai_query to turn each CSA's eligible-collateral clause into
structured rows in `eligible_collateral`, which the app's CDM export then emits
as `creditSupportAgreementElections.eligibleCollateral[]`.
"""
import json
import re
import sys

import dbx

MODEL = dbx.LLM_MODEL  # from config.env

PROMPT = (
    "From the ISDA Credit Support Annex text below, extract the ELIGIBLE "
    "COLLATERAL schedule as structured rules. Return ONLY a JSON array; each "
    'element: {"asset_type": string, "issuer": string or null, '
    '"maturity_band": string or null, "valuation_percentage": number (0-100), '
    '"haircut_percentage": number (100 - valuation_percentage), '
    '"currency": string or null}. One row per asset class / maturity band. '
    "TEXT:\n")


def annotated_text(w, r, doc_id):
    rows = dbx.run_sql(w, "SELECT chunk_text FROM %s WHERE doc_id='%s' ORDER BY "
                       "page" % (r["chunks_table"], doc_id))
    return " ".join(x["chunk_text"] for x in rows)


def ensure_table(w, r):
    dbx.run_sql(w, """
    CREATE TABLE IF NOT EXISTS {t} (
        doc_id STRING, asset_type STRING, issuer STRING, maturity_band STRING,
        valuation_percentage DOUBLE, haircut_percentage DOUBLE, currency STRING,
        extracted_at TIMESTAMP
    ) TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """.format(t=r["collateral_table"]))


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    r["collateral_table"] = "%s.%s.eligible_collateral" % (r["catalog"],
                                                           r["schema"])
    dbx.save_resolved(r)
    ensure_table(w, r)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    ids = [only] if only else [d["doc_id"] for d in dbx.run_sql(
        w, "SELECT doc_id FROM %s ORDER BY doc_id" % r["documents_table"])]
    if not only:
        dbx.run_sql(w, "DELETE FROM %s" % r["collateral_table"])

    total = 0
    for did in ids:
        prompt = (PROMPT + annotated_text(w, r, did)).replace("'", "''")
        try:
            raw = dbx.run_sql(w, "SELECT ai_query('%s','%s') AS o"
                              % (MODEL, prompt))[0]["o"]
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            data = json.loads(m.group(0) if m else raw)
            vals = []
            for d in data:
                at = str(d.get("asset_type", "")).replace("'", "''")[:200]
                iss = str(d.get("issuer") or "").replace("'", "''")[:200]
                mb = str(d.get("maturity_band") or "").replace("'", "''")[:120]
                cur = str(d.get("currency") or "").replace("'", "''")[:10]

                def num(x):
                    try:
                        return float(x)
                    except (TypeError, ValueError):
                        return "NULL"
                vp, hc = num(d.get("valuation_percentage")), num(
                    d.get("haircut_percentage"))
                vals.append("('%s','%s','%s','%s',%s,%s,'%s',current_timestamp())"
                            % (did, at, iss, mb, vp, hc, cur))
            if vals:
                dbx.run_sql(w, "INSERT INTO %s VALUES %s"
                            % (r["collateral_table"], ",".join(vals)))
                total += len(vals)
            print("collateral %-6s -> %d rules" % (did, len(vals)))
        except Exception as e:
            print("FAILED %s: %s" % (did, str(e)[:160]))

    # app-SP grants happen in 05_deploy_app.py
    print("\nDONE: %d collateral rules." % total)


if __name__ == "__main__":
    main()
