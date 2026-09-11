"""Step 5 (run LAST): grant the app service principal on ALL objects, then
ship config.json, upload the source, and deploy the Streamlit app.

The app itself is created earlier by 00_create_app.py (so its SP exists before
the build steps). This step consolidates every grant in one place and reads the
SP + all names from config.env / resolved.json.
"""
import json
import os

from databricks.sdk.service.apps import AppDeployment
from databricks.sdk.service.sql import (WarehouseAccessControlRequest,
                                         WarehousePermissionLevel)

import dbx

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")


def _grant_sql(w, stmt):
    try:
        dbx.run_sql(w, stmt)
        print("  granted:", stmt.split(" TO ")[0])
    except Exception as e:
        print("  grant note:", str(e)[:120])


def _grant_endpoint(w, vsc, name):
    try:
        ep = vsc.get_endpoint(name)
        eid = ep.get("id") or ep.get("endpoint_id")
        w.api_client.do("PATCH",
                        "/api/2.0/permissions/vector-search-endpoints/%s" % eid,
                        body={"access_control_list": [
                            {"service_principal_name": dbx.APP_SP,
                             "permission_level": "CAN_USE"}]})
        print("  granted CAN_USE on endpoint", name)
    except Exception as e:
        print("  endpoint grant note (%s): %s" % (name, str(e)[:100]))


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    sp = dbx.APP_SP
    if not sp:
        raise SystemExit("APP_SP is empty — run deploy/00_create_app.py first.")

    # 1. config.json shipped with the app source
    cfg = {"warehouse_id": dbx.WAREHOUSE_ID, "catalog": r["catalog"],
           "schema": r["schema"], "documents_table": r["documents_table"],
           "chunks_table": r["chunks_table"], "audit_table": r["audit_table"],
           "vs_endpoint": r["vs_endpoint"], "vs_index": r["vs_index"],
           "llm_model": dbx.LLM_MODEL}
    for k in ("fts_endpoint", "fts_index", "extractions_table",
              "collateral_table"):
        if r.get(k):
            cfg[k] = r[k]
    with open(os.path.join(APP_DIR, "config.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    print("wrote app/config.json")

    # 2. all SQL grants (each best-effort; some objects may not exist yet)
    cat, sch, vol = r["catalog"], r["schema"], r["volume"]
    _grant_sql(w, "GRANT USE CATALOG ON CATALOG `%s` TO `%s`" % (cat, sp))
    _grant_sql(w, "GRANT USE SCHEMA ON SCHEMA `%s`.`%s` TO `%s`" % (cat, sch, sp))
    _grant_sql(w, "GRANT READ VOLUME ON VOLUME `%s`.`%s`.`%s` TO `%s`"
               % (cat, sch, vol, sp))
    for tbl in (r["documents_table"], r["chunks_table"], r.get("collateral_table"),
                r.get("vs_index"), r.get("fts_index")):
        if tbl:
            _grant_sql(w, "GRANT SELECT ON TABLE %s TO `%s`" % (tbl, sp))
    for tbl in (r["audit_table"], r.get("extractions_table")):
        if tbl:
            _grant_sql(w, "GRANT SELECT, MODIFY ON TABLE %s TO `%s`" % (tbl, sp))

    # 3. compute grants (warehouse + vector-search endpoints)
    try:
        w.warehouses.update_permissions(
            warehouse_id=dbx.WAREHOUSE_ID, access_control_list=[
                WarehouseAccessControlRequest(
                    service_principal_name=sp,
                    permission_level=WarehousePermissionLevel.CAN_USE)])
        print("  granted CAN_USE on warehouse", dbx.WAREHOUSE_ID)
    except Exception as e:
        print("  warehouse grant note:", str(e)[:100])
    try:
        from databricks.vector_search.client import VectorSearchClient
        vsc = VectorSearchClient(workspace_url=r["host"],
                                 personal_access_token=dbx.bearer(w),
                                 disable_notice=True)
        _grant_endpoint(w, vsc, dbx.VS_ENDPOINT)
        if r.get("fts_endpoint"):
            _grant_endpoint(w, vsc, dbx.FTS_ENDPOINT)
    except Exception as e:
        print("  vs endpoint grants skipped:", str(e)[:100])
    print("(FM endpoints %s / %s are system endpoints — open, no grant needed)"
          % (dbx.LLM_MODEL, dbx.EMBED_MODEL))

    # 4. upload source + deploy
    src_ws = "/Workspace/Users/%s/isda_contract_search_src" % (
        w.current_user.me().user_name)
    _upload_dir(w, APP_DIR, src_ws)
    print("uploaded source to", src_ws)
    dep = w.apps.deploy(app_name=dbx.APP_NAME,
                        app_deployment=AppDeployment(source_code_path=src_ws)
                        ).result()
    print("deploy state:", dep.status.state if dep.status else "?")
    print("\nAPP URL:", w.apps.get(name=dbx.APP_NAME).url)


def _upload_dir(w, local_dir, ws_dir):
    from databricks.sdk.service.workspace import ImportFormat
    w.workspace.mkdirs(ws_dir)
    for fn in os.listdir(local_dir):
        lp = os.path.join(local_dir, fn)
        if not os.path.isfile(lp) or fn.endswith(".pyc"):
            continue
        with open(lp, "rb") as fh:
            w.workspace.upload("%s/%s" % (ws_dir, fn), fh.read(),
                               format=ImportFormat.AUTO, overwrite=True)


if __name__ == "__main__":
    main()
