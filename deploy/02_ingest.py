"""Step 2: Parse the 20 PDFs into `documents` and `document_chunks`.

Parsing is done locally with pypdf (the PDFs carry a clean text layer). For
scanned inputs the production path is Databricks `ai_parse_document` - noted in
the plan. Parsed rows are written as NDJSON to the staging volume and loaded
into Delta with `read_files`. Chunks table gets a primary key + Change Data
Feed so it can back a Delta Sync vector index.
"""
import io
import json
import os

import pypdf

import dbx

CONTRACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts")


def parse_pdf_bytes(b):
    reader = pypdf.PdfReader(io.BytesIO(b))
    pages = []
    for i, pg in enumerate(reader.pages, start=1):
        txt = (pg.extract_text() or "").strip()
        # collapse runaway whitespace but keep it readable
        txt = " ".join(txt.split())
        pages.append(txt)
    return pages


def main():
    w = dbx.client()
    r = dbx.load_resolved()

    manifest = json.load(open(os.path.join(CONTRACTS_DIR, "manifest.json")))
    by_id = {m["doc_id"]: m for m in manifest}

    doc_rows, chunk_rows = [], []
    for m in manifest:
        path = os.path.join(CONTRACTS_DIR, m["file_name"])
        pages = parse_pdf_bytes(open(path, "rb").read())
        full_text = "\n\n".join(pages)
        doc_rows.append({
            "doc_id": m["doc_id"], "file_name": m["file_name"],
            "counterparty": m["counterparty"],
            "counterparty_short": m["counterparty_short"],
            "counterparty_type": m["counterparty_type"],
            "jurisdiction": m["jurisdiction"], "lei": m["lei"],
            "governing_law": m["governing_law"], "base_currency": m["base_currency"],
            "threshold": m["threshold"],
            "minimum_transfer_amount": m["minimum_transfer_amount"],
            "independent_amount": m["independent_amount"],
            "cross_default_threshold": m["cross_default_threshold"],
            "automatic_early_termination": m["automatic_early_termination"],
            "csa_type": m["csa_type"], "products": m["products"],
            "specified_entity": m["specified_entity"],
            "additional_termination_events": m["additional_termination_events"],
            "effective_date": m["effective_date"],
            "agreement_type": m["agreement_type"],
            "page_count": len(pages), "full_text": full_text,
        })
        for idx, txt in enumerate(pages, start=1):
            if not txt:
                continue
            chunk_rows.append({
                "chunk_id": "%s_p%d" % (m["doc_id"], idx),
                "doc_id": m["doc_id"], "page": idx, "chunk_index": idx - 1,
                "chunk_text": txt, "char_len": len(txt),
            })
    print("parsed %d docs -> %d chunks" % (len(doc_rows), len(chunk_rows)))

    def upload_ndjson(rows, subdir, name):
        buf = "\n".join(json.dumps(x) for x in rows).encode("utf-8")
        dest = "%s/%s/%s" % (r["staging_path"], subdir, name)
        w.files.upload(dest, io.BytesIO(buf), overwrite=True)
        print("staged", dest)

    upload_ndjson(doc_rows, "documents", "documents.json")
    upload_ndjson(chunk_rows, "chunks", "chunks.json")

    docs_stage = "%s/documents" % r["staging_path"]
    chunks_stage = "%s/chunks" % r["staging_path"]

    dbx.run_sql(w, """
    CREATE OR REPLACE TABLE {tbl} AS
    SELECT doc_id, file_name, counterparty, counterparty_short, counterparty_type,
           jurisdiction, lei, governing_law, base_currency, threshold,
           minimum_transfer_amount, independent_amount, cross_default_threshold,
           CAST(automatic_early_termination AS BOOLEAN) AS automatic_early_termination,
           csa_type, products, specified_entity, additional_termination_events,
           CAST(effective_date AS DATE) AS effective_date, agreement_type,
           CAST(page_count AS INT) AS page_count, full_text,
           current_timestamp() AS ingested_at
    FROM read_files('{stage}', format => 'json', multiLine => false)
    """.format(tbl=r["documents_table"], stage=docs_stage))
    print("built", r["documents_table"])

    dbx.run_sql(w, """
    CREATE OR REPLACE TABLE {tbl}
    TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
    SELECT CAST(chunk_id AS STRING) AS chunk_id, doc_id, CAST(page AS INT) AS page,
           CAST(chunk_index AS INT) AS chunk_index, chunk_text,
           CAST(char_len AS INT) AS char_len
    FROM read_files('{stage}', format => 'json', multiLine => false)
    """.format(tbl=r["chunks_table"], stage=chunks_stage))
    dbx.run_sql(w, "ALTER TABLE %s ALTER COLUMN chunk_id SET NOT NULL"
                % r["chunks_table"])
    dbx.run_sql(w, "ALTER TABLE %s ADD CONSTRAINT pk_%s PRIMARY KEY (chunk_id)"
                % (r["chunks_table"], "isda_chunks"))
    print("built", r["chunks_table"], "(PK + CDF)")

    dc = dbx.run_sql(w, "SELECT count(*) c FROM %s" % r["documents_table"])
    cc = dbx.run_sql(w, "SELECT count(*) c FROM %s" % r["chunks_table"])
    print("row counts -> documents:", dc[0]["c"], " chunks:", cc[0]["c"])


if __name__ == "__main__":
    main()
