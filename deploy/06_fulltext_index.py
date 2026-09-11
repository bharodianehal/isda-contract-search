"""Step 6 (Option B): Full-text search index on a STORAGE-OPTIMIZED endpoint.

This is the SECOND way to do keyword search, alongside the SQL ILIKE lane
(Option A). It creates a Databricks-managed BM25 full-text index over the same
`document_chunks` table - NO embeddings - and grants the app SP access.

Beta feature: full-text (index_subtype=FULL_TEXT) is only supported on
STORAGE_OPTIMIZED endpoints and requires TRIGGERED sync.
"""
import time

from databricks.vector_search.client import VectorSearchClient

import dbx

FTS_ENDPOINT = dbx.FTS_ENDPOINT  # from config.env


def bearer(w):
    return dbx.bearer(w)


def wait_endpoint(vsc, name, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            ep = vsc.get_endpoint(name)
            state = (ep.get("endpoint_status", {}) or {}).get("state", "")
            print("  endpoint state:", state)
            if state == "ONLINE":
                return
        except Exception as e:
            print("  (waiting)", str(e)[:80])
        time.sleep(20)
    raise TimeoutError("endpoint not ONLINE in time")


def wait_index(idx, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = idx.describe()
        st = d.get("status", {}) or {}
        ready = st.get("ready", False)
        print("  index ready=%s state=%s rows=%s" % (
            ready, st.get("detailed_state", st.get("message", "")),
            st.get("indexed_row_count", 0)))
        if ready:
            return
        time.sleep(20)
    raise TimeoutError("index not READY in time")


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    vsc = VectorSearchClient(workspace_url=r["host"],
                             personal_access_token=bearer(w), disable_notice=True)

    fts_index = "%s.%s.document_chunks_fts_index" % (r["catalog"], r["schema"])

    # 1) endpoint (created in the feasibility probe; ensure + wait ONLINE)
    existing = [e["name"] for e in (vsc.list_endpoints().get("endpoints", []) or [])]
    if FTS_ENDPOINT not in existing:
        print("creating STORAGE_OPTIMIZED endpoint", FTS_ENDPOINT)
        vsc.create_endpoint(name=FTS_ENDPOINT, endpoint_type="STORAGE_OPTIMIZED")
    wait_endpoint(vsc, FTS_ENDPOINT)

    # 2) full-text index (no embeddings)
    try:
        idx = vsc.get_index(endpoint_name=FTS_ENDPOINT, index_name=fts_index)
        print("index exists", fts_index)
    except Exception:
        print("creating FULL_TEXT index", fts_index)
        idx = vsc.create_delta_sync_index(
            endpoint_name=FTS_ENDPOINT,
            index_name=fts_index,
            source_table_name=r["chunks_table"],
            pipeline_type="TRIGGERED",
            primary_key="chunk_id",
            columns_to_sync=["chunk_id", "doc_id", "page", "chunk_text"],
            index_subtype="FULL_TEXT",
        )
    wait_index(idx)
    try:
        idx.sync()
        print("triggered sync")
    except Exception as e:
        print("sync note:", str(e)[:100])

    # 3) smoke test FULL_TEXT query
    res = idx.similarity_search(query_text="Automatic Early Termination",
                                columns=["chunk_id", "doc_id", "page"],
                                num_results=5, query_type="FULL_TEXT")
    n = len((res.get("result", {}) or {}).get("data_array", []) or [])
    print("smoke FULL_TEXT rows:", n)

    # persist coordinates (app-SP grants happen in 05_deploy_app.py)
    r["fts_endpoint"] = FTS_ENDPOINT
    r["fts_index"] = fts_index
    dbx.save_resolved(r)
    print("\nDONE Option B ready:", fts_index)


if __name__ == "__main__":
    main()
