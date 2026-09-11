"""Step 3: Create the Mosaic AI Vector Search endpoint + Delta Sync index.

Managed embeddings (databricks-gte-large-en) over chunk_text; the index is used
in HYBRID mode by the app (Lane 2). Waits for endpoint + index to be ONLINE.
"""
import time

from databricks.vector_search.client import VectorSearchClient

import dbx

EMBED_MODEL = dbx.EMBED_MODEL


def bearer(w):
    return dbx.bearer(w)


def wait_endpoint(vsc, name, timeout=900):
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
        detail = st.get("detailed_state", st.get("message", ""))
        cnt = st.get("indexed_row_count", 0)
        print("  index ready=%s state=%s rows=%s" % (ready, detail, cnt))
        if ready:
            return
        time.sleep(20)
    raise TimeoutError("index not READY in time")


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    vsc = VectorSearchClient(workspace_url=r["host"],
                             personal_access_token=bearer(w),
                             disable_notice=True)

    ep = r["vs_endpoint"]
    existing = [e["name"] for e in (vsc.list_endpoints().get("endpoints", []) or [])]
    if ep not in existing:
        print("creating endpoint", ep)
        vsc.create_endpoint(name=ep, endpoint_type="STANDARD")
    else:
        print("endpoint exists", ep)
    wait_endpoint(vsc, ep)

    idx_name = r["vs_index"]
    try:
        idx = vsc.get_index(endpoint_name=ep, index_name=idx_name)
        print("index exists", idx_name)
    except Exception:
        print("creating delta-sync index", idx_name)
        idx = vsc.create_delta_sync_index(
            endpoint_name=ep,
            index_name=idx_name,
            source_table_name=r["chunks_table"],
            pipeline_type="TRIGGERED",
            primary_key="chunk_id",
            embedding_source_column="chunk_text",
            embedding_model_endpoint_name=EMBED_MODEL,
        )
    wait_index(idx)
    try:
        idx.sync()
        print("triggered sync")
    except Exception as e:
        print("sync note:", str(e)[:100])

    # smoke test
    res = idx.similarity_search(query_text="automatic early termination on downgrade",
                                columns=["chunk_id", "doc_id", "page"],
                                num_results=3, query_type="HYBRID")
    print("smoke hybrid search rows:",
          len((res.get("result", {}) or {}).get("data_array", []) or []))
    print("DONE vector search ready:", idx_name)


if __name__ == "__main__":
    main()
