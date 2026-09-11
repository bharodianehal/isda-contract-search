# ISDA Contract Search

An AI app for Legal Analysts to search, extract, and analyze ISDA master
agreements & CSAs on Databricks. Keyword search (recall-first), AI clause
extraction into the **FINOS Common Domain Model (CDM)**, portfolio analytics,
and grounded Q&A — all governed by Unity Catalog, with a full audit trail.

See **[plan/SEARCH_IMPLEMENTATION_PLAN.md](plan/SEARCH_IMPLEMENTATION_PLAN.md)**
and **[plan/ENHANCEMENT_PLAN.md](plan/ENHANCEMENT_PLAN.md)** for the design.

## The app (7 tabs)
- **📊 Portfolio** — analytics with click-to-filter charts + agreements table (open/download a doc)
- **📚 Documents** — the 20-agreement library (open in-app page preview / download)
- **🧬 Extract** — AI clause register (value · page · snippet) + Digitize → CDM (icons/popups)
- **🔎 Search** — keyword search: **Method A** (Direct / Semantic / Hybrid) or **Method B** (BM25 full-text)
- **💬 Ask** — grounded natural-language Q&A with `[doc_id]` citations
- **🕑 History** — who / when / what / result audit
- **🏗️ Architecture** — build/search/AI/technical diagrams

## Configuration — one place
**All environment-specific settings live in [`config.env`](config.env)** —
profile, host, warehouse, catalog/schema/volume, endpoints, models, app name,
and the app service-principal id. Every deploy script reads it via `deploy/dbx.py`.

**Secrets are NOT in the repo.** Authentication uses the Databricks CLI (OAuth);
the token is cached in `~/.databrickscfg` (outside the repo). If a step ever
needs a PAT, put it in `.env.local` (git-ignored) — never commit it.

## Layout
```
config.env      ← single central config (edit this per environment)
contracts/      20 synthetic ISDA PDFs + manifest.json
generator/      scripts that produce the PDFs
plan/           design + enhancement plans
deploy/         deployment pipeline (dbx.py = config loader + helpers)
app/            Streamlit app (app.py, cdm.py, config.py, requirements.txt)
```

## Rebuild elsewhere (new workspace / machine)
1. **Clone** the repo.
2. **Edit `config.env`** — set `DBX_PROFILE`, `DBX_HOST`, `DBX_WAREHOUSE_ID`,
   catalog/schema, and clear `APP_SP` (a fresh SP is minted on first deploy).
3. **Authenticate:** `databricks auth login --host <DBX_HOST> --profile <DBX_PROFILE>`
4. **Local venv:**
   ```bash
   uv venv .venv
   uv pip install --python .venv/bin/python reportlab pypdf databricks-sdk \
       databricks-vectorsearch jsonschema pandas pymupdf
   ```
5. **Generate contracts** (if not present): `cd generator && ../.venv/bin/python generate_contracts.py`
6. **Deploy everything:** `cd ../deploy && ../.venv/bin/python run_all.py`
   Order: `00_create_app` (mints APP_SP → config.env) → `01_setup_uc` →
   `02_ingest` → `03_vector_search` → `04_audit` → `validate_search` →
   `06_fulltext_index` → `07_extract_clauses` → `08_eligible_collateral` →
   `05_deploy_app` (grants the app SP on everything + deploys).

### Notes
- **Method B (full-text BM25)** is a Beta feature — enable the **Full Text**
  workspace preview (Settings → Previews) before `06`, else it's skipped and
  Method A still works.
- A standalone catalog is attempted; if disallowed it falls back to a schema
  named `ISDA_CATALOG` inside `ISDA_FALLBACK_CATALOG`.
- App requirements are in `app/requirements.txt` (Databricks App installs them).

## Search methods
| | Method A — Vector search | Method B — Full-text (BM25) |
|---|---|---|
| Direct | SQL `ILIKE`, 100% recall | — |
| Semantic | Vector ANN (meaning) | — |
| Hybrid *(default)* | Direct ∪ Vector HYBRID | — |
| — | — | Managed BM25 index (Beta, scales to billions) |
