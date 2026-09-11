"""Shared Databricks helpers for the ISDA search deployment scripts.

ALL environment-specific configuration is read from ../config.env (a single
central file). Environment variables override config.env values. Authentication
is via the Databricks CLI (OAuth) — NOT stored in the repo.

All scripts run LOCALLY against the workspace via the CLI profile, using the SQL
Statement Execution API and the Files API.
"""
import os

from databricks.sdk import WorkspaceClient

_HERE = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(_HERE, "..", "config.env")
RESOLVED_PATH = os.path.join(_HERE, "resolved.json")


def _load_config():
    """Parse config.env (KEY=VALUE). os.environ takes precedence."""
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


_CFG = _load_config()


def cfg(key, default=""):
    return os.environ.get(key, _CFG.get(key, default))


# --- centralized settings (config.env, env-overridable) ---------------------
PROFILE = cfg("DBX_PROFILE", "sa-ccr")
HOST = cfg("DBX_HOST", "")
WAREHOUSE_ID = cfg("DBX_WAREHOUSE_ID", "78e7294c42f67d58")
PREF_CATALOG = cfg("ISDA_CATALOG", "isda_search")
FALLBACK_CATALOG = cfg("ISDA_FALLBACK_CATALOG", "serverless_stable_pdu5ct_catalog")
SCHEMA = cfg("ISDA_SCHEMA", "isda")
VOLUME = cfg("ISDA_VOLUME", "contracts")
VS_ENDPOINT = cfg("VS_ENDPOINT", "isda-search-endpoint")
FTS_ENDPOINT = cfg("FTS_ENDPOINT", "isda-fts-endpoint")
EMBED_MODEL = cfg("EMBED_MODEL", "databricks-gte-large-en")
LLM_MODEL = cfg("LLM_MODEL", "databricks-claude-sonnet-4-6")
APP_NAME = cfg("APP_NAME", "isda-contract-search")
APP_SP = cfg("APP_SP", "")


def set_config(key, value):
    """Persist a value back into config.env (e.g., APP_SP after app creation)."""
    lines, found = [], False
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "=") or line.strip().startswith(key + " ="):
            lines[i] = "%s=%s\n" % (key, value)
            found = True
            break
    if not found:
        lines.append("%s=%s\n" % (key, value))
    with open(CONFIG_PATH, "w") as f:
        f.writelines(lines)
    globals()[{"APP_SP": "APP_SP"}.get(key, key)] = value


def client():
    return WorkspaceClient(profile=PROFILE)


def bearer(w):
    """Extract a bearer token from the SDK config (works for any auth type)."""
    return w.config.authenticate()["Authorization"].split(" ", 1)[1]


def run_sql(w, statement, catalog=None, schema=None, wait="50s"):
    """Execute a SQL statement on the serverless warehouse; return rows as
    dicts. Raises on error."""
    import time
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID, statement=statement,
        catalog=catalog, schema=schema, wait_timeout=wait,
    )
    while resp.status and resp.status.state and resp.status.state.value in (
            "PENDING", "RUNNING"):
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    state = resp.status.state.value if resp.status and resp.status.state else "?"
    if state != "SUCCEEDED":
        msg = resp.status.error.message if resp.status and resp.status.error else ""
        raise RuntimeError("SQL failed [%s]: %s\n---\n%s" % (state, msg,
                                                             statement[:500]))
    cols, rows = [], []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        cols = [c.name for c in resp.manifest.schema.columns]
    if resp.result and resp.result.data_array:
        for r in resp.result.data_array:
            rows.append(dict(zip(cols, r)))
    return rows


import json  # noqa: E402


def save_resolved(d):
    with open(RESOLVED_PATH, "w") as f:
        json.dump(d, f, indent=2)


def load_resolved():
    with open(RESOLVED_PATH) as f:
        return json.load(f)
