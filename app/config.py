"""App configuration. Reads config.json (shipped with the app at deploy time)
and allows environment-variable overrides. Falls back to sensible defaults."""
import json
import os

_HERE = os.path.dirname(__file__)

_defaults = {
    "warehouse_id": "78e7294c42f67d58",
    "catalog": "isda_search",
    "schema": "isda",
    "documents_table": "isda_search.isda.documents",
    "chunks_table": "isda_search.isda.document_chunks",
    "audit_table": "isda_search.isda.search_audit",
    "vs_endpoint": "isda-search-endpoint",
    "vs_index": "isda_search.isda.document_chunks_index",
    "fts_endpoint": "isda-fts-endpoint",
    "fts_index": "isda_search.isda.document_chunks_fts_index",
    "extractions_table": "isda_search.isda.clause_extractions",
    "collateral_table": "isda_search.isda.eligible_collateral",
    "llm_model": "databricks-claude-sonnet-4-6",
}

_cfg = dict(_defaults)
_path = os.path.join(_HERE, "config.json")
if os.path.exists(_path):
    try:
        _cfg.update({k: v for k, v in json.load(open(_path)).items() if v})
    except Exception:
        pass


def get(key):
    return os.environ.get(key.upper(), _cfg.get(key))
