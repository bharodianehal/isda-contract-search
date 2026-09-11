"""Step 1: Create Unity Catalog objects and upload the 20 ISDA PDFs.

Tries to create a standalone catalog `isda_search`; if the workspace disallows
it, falls back to a schema `isda_search` inside the shared serverless catalog.
Writes the resolved coordinates to deploy/resolved.json for later steps + app.
"""
import glob
import os

import dbx

CONTRACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts")


def main():
    w = dbx.client()
    me = w.current_user.me()
    print("Authenticated as:", me.user_name)

    catalog = dbx.PREF_CATALOG
    try:
        dbx.run_sql(w, "CREATE CATALOG IF NOT EXISTS %s" % catalog)
        dbx.run_sql(w, "USE CATALOG %s" % catalog)
        print("Using standalone catalog:", catalog)
    except Exception as e:
        print("Catalog create failed (%s) -> falling back to schema in %s"
              % (str(e)[:120], dbx.FALLBACK_CATALOG))
        catalog = dbx.FALLBACK_CATALOG

    schema = dbx.SCHEMA if catalog != dbx.FALLBACK_CATALOG else "isda_search"
    volume = dbx.VOLUME

    dbx.run_sql(w, "CREATE SCHEMA IF NOT EXISTS `%s`.`%s`" % (catalog, schema))
    dbx.run_sql(w, "CREATE VOLUME IF NOT EXISTS `%s`.`%s`.`%s`"
                % (catalog, schema, volume))
    print("Schema + volume ready: %s.%s (volume %s)" % (catalog, schema, volume))

    vol_root = "/Volumes/%s/%s/%s" % (catalog, schema, volume)
    contracts_path = vol_root + "/contracts"
    staging_path = vol_root + "/staging"

    # Upload PDFs via the Files API.
    pdfs = sorted(glob.glob(os.path.join(CONTRACTS_DIR, "*.pdf")))
    for p in pdfs:
        dest = "%s/%s" % (contracts_path, os.path.basename(p))
        with open(p, "rb") as fh:
            w.files.upload(dest, fh, overwrite=True)
        print("uploaded", os.path.basename(p))
    # Upload the manifest too (used by the ingest step / app metadata).
    with open(os.path.join(CONTRACTS_DIR, "manifest.json"), "rb") as fh:
        w.files.upload("%s/manifest.json" % contracts_path, fh, overwrite=True)

    resolved = {
        "profile": dbx.PROFILE,
        "warehouse_id": dbx.WAREHOUSE_ID,
        "catalog": catalog,
        "schema": schema,
        "volume": volume,
        "vol_root": vol_root,
        "contracts_path": contracts_path,
        "staging_path": staging_path,
        "documents_table": "%s.%s.documents" % (catalog, schema),
        "chunks_table": "%s.%s.document_chunks" % (catalog, schema),
        "audit_table": "%s.%s.search_audit" % (catalog, schema),
        "vs_endpoint": dbx.VS_ENDPOINT,
        "vs_index": "%s.%s.document_chunks_index" % (catalog, schema),
        "host": w.config.host,
    }
    dbx.save_resolved(resolved)
    print("\nResolved coordinates written to deploy/resolved.json:")
    for k, v in resolved.items():
        print("  %-18s %s" % (k, v))
    print("\nUploaded %d PDFs to %s" % (len(pdfs), contracts_path))


if __name__ == "__main__":
    main()
