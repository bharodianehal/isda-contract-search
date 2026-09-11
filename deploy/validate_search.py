"""Golden-keyword recall regression for the exact (lexical) search lane.

Ground truth = independently parse the PDFs locally and record which documents
literally contain each golden term. Then run the app's exact-lane SQL against
`document_chunks` and assert the returned document set is IDENTICAL. This is the
continuous proof that the "no missed documents" guarantee holds.
"""
import io
import json
import os

import pypdf

import dbx

CONTRACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts")

GOLDEN = [
    "Goldman Sachs", "Morgan Stanley", "State Street", "BNY Mellon",
    "Credit Default Swaps", "Total Return Swaps", "Inflation Swaps",
    "Net Asset Value Decline", "Key Person Event", "Investment Manager Termination",
    "Ratings Downgrade below A-", "JPY 1,500,000,000",
    "W22LROWP2IHZNBB6K528",          # Goldman LEI (unique)
    "Automatic Early Termination",    # in boilerplate -> expected: ALL docs
    "USD 50,000,000",
]


def local_ground_truth():
    manifest = json.load(open(os.path.join(CONTRACTS_DIR, "manifest.json")))
    texts = {}
    for m in manifest:
        rd = pypdf.PdfReader(os.path.join(CONTRACTS_DIR, m["file_name"]))
        texts[m["doc_id"]] = " ".join(
            " ".join((p.extract_text() or "").split()) for p in rd.pages).lower()
    return texts


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    truth = local_ground_truth()

    failures = 0
    for term in GOLDEN:
        expected = {d for d, t in truth.items() if term.lower() in t}
        rows = dbx.run_sql(w, """
            SELECT DISTINCT doc_id FROM {tbl}
            WHERE lower(chunk_text) LIKE lower('%{q}%')
        """.format(tbl=r["chunks_table"], q=term.replace("'", "''")))
        actual = {row["doc_id"] for row in rows}
        ok = actual == expected
        failures += 0 if ok else 1
        missed = expected - actual
        print("%-4s %-34s expected=%2d actual=%2d%s"
              % ("PASS" if ok else "FAIL", term[:34], len(expected), len(actual),
                 "" if ok else "  MISSED=%s" % sorted(missed)))

    print("\n%s: %d/%d golden terms have exact recall == ground truth"
          % ("ALL PASS" if failures == 0 else "FAILURES", len(GOLDEN) - failures,
             len(GOLDEN)))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
