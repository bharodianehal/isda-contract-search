# ISDA Contract Search — Implementation Plan

**Author:** Field Engineering · **Date:** 2026-09-10 · **Workspace:** `fevm-serverless-stable-pdu5ct` (AWS us-east-2)
**Goal:** Let a Legal Analyst search a library of ISDA template contracts by keyword, with **no missed documents**, and see *where* each keyword appears in each document — plus a full audit trail of who searched what, when, and with what result.

---

## 1. The core requirement: recall must be 100% on exact keywords

The business rule is *"we should not miss the documents for the keyword search."* In information-retrieval terms this is a **recall-critical** requirement: a false negative (a document that contains the keyword but is not returned) is unacceptable. This single constraint drives the whole architecture.

### Why pure vector / semantic search is *not* sufficient on its own
Mosaic AI Vector Search (semantic search over embeddings) is excellent for *conceptual* matching — "find contracts about early termination on a downgrade" — but it is **lossy by construction**:

- Embeddings compress a passage into a fixed-length vector; rare tokens, exact identifiers (an LEI like `W22LROWP2IHZNBB6K528`, a precise figure like `USD 50,000,000`, a party name), and exact clause labels can be **washed out**.
- Approximate-nearest-neighbour retrieval returns the *top-k* by cosine similarity — a document that literally contains the keyword can rank below k and be dropped.
- Therefore semantic-only search **can miss an exact match**, which violates the requirement.

### The decision: a two-lane hybrid, with a **recall-guaranteed lexical lane** as the backbone
| Lane | Mechanism | Guarantees | Catches |
|------|-----------|------------|---------|
| **Lane 1 — Exact / lexical (backbone)** | Full-text keyword match in Databricks SQL over the parsed chunk text (`ILIKE` / `rlike` regex / `contains`) | **100% recall on exact keywords** — every chunk that literally contains the term is returned; zero false negatives | Party names, LEIs, currency amounts, clause labels ("Automatic Early Termination"), defined terms |
| **Lane 2 — Semantic (recall-expanding)** | Mosaic AI Vector Search index in **hybrid mode** (vector similarity + built-in keyword scoring) | Adds conceptually-related hits | Synonyms & paraphrase ("close-out netting" ≈ "termination netting"), fuzzy intent |

Results from both lanes are **merged, de-duplicated by document, and labelled by match type** (`exact` / `semantic`). The exact lane alone satisfies the "don't miss anything" rule; the semantic lane only ever *adds* documents, never removes them. This is the safe way to combine the two: recall can only go up.

> Databricks Vector Search natively supports **hybrid search** (`query_type="HYBRID"`), which already blends keyword and vector scoring in one call. We still keep the independent SQL exact lane as the guarantee-of-record, because hybrid ranking is still top-k and we want a lane with *no* k-cutoff for the corpus at this size (20 docs / ~140 chunks — an exhaustive scan is trivially cheap and provably complete).

---

## 2. Options considered (per https://docs.databricks.com/aws/en/ai-search/)

| Option | What it is | Fit for "no missed docs" keyword search | Verdict |
|--------|-----------|------------------------------------------|---------|
| **A. SQL full-text / `ILIKE` / regex over parsed text** | Exhaustive string match in DBSQL | ✅ Perfect recall on exact terms; cheap at this scale | **Chosen — Lane 1 backbone** |
| **B. Mosaic AI Vector Search — Delta Sync index, managed embeddings, hybrid** | Managed ANN index auto-synced from a Delta table; Databricks computes embeddings; hybrid keyword+vector | ✅ Great for concepts; ⚠️ top-k, lossy — not a recall guarantee alone | **Chosen — Lane 2** |
| C. Vector Search self-managed embeddings | You compute/maintain embeddings | More ops burden, no benefit here | Rejected |
| D. `ai_query` + LLM read-every-doc | Ask an LLM per document | Slow, costly, non-deterministic recall | Rejected (but LLM used *only* to summarize the matched set in the app) |
| E. External engine (OpenSearch/Elastic) | Dedicated full-text engine | Real BM25, but adds infra outside UC governance | Overkill for 20 docs; revisit only at 10k+ docs |

**Ingestion / parsing:** Databricks `ai_parse_document` is the production path for turning PDFs (including scanned/OCR) into structured text. For this corpus the PDFs carry a clean embedded text layer, so we parse deterministically with `pypdf` in the ingestion job and keep `ai_parse_document` as the documented upgrade path for scanned inputs.

---

## 3. Target architecture

```
UC Volume (PDFs)
  /Volumes/isda_search/isda/contracts/*.pdf
        │  (ingestion job / notebook)
        ▼
  parse (pypdf → text; ai_parse_document for scans)
        │
        ├─►  isda_search.isda.documents          one row/doc + full_text + metadata
        │
        └─►  isda_search.isda.document_chunks     page-level chunks (CDF enabled)
                    │
                    ▼
        Mosaic AI Vector Search
          endpoint: isda-search-endpoint
          index:    isda_search.isda.document_chunks_index   (Delta Sync, managed embeddings, HYBRID)

  Databricks App (Streamlit, FastAPI-served)
     ├─ Lane 1  exact  → DBSQL ILIKE/regex over document_chunks  (100% recall)
     ├─ Lane 2  semantic → vector index .similarity_search(query_type="HYBRID")
     ├─ merge + dedupe by doc + highlight keyword + page ref
     ├─ (optional) ai_query summary of the matched set
     └─ writes one row per search → isda_search.isda.search_audit   (who/when/what/result)
```

### Data model
- **`documents`** — `doc_id, file_name, counterparty, counterparty_type, jurisdiction, lei, governing_law, base_currency, cross_default_threshold, automatic_early_termination, csa_type, products (array), effective_date, agreement_type, full_text, page_count, ingested_at`.
- **`document_chunks`** — `chunk_id (PK), doc_id, page, chunk_index, chunk_text, char_len`. **Change Data Feed ON** (required for a Delta Sync vector index).
- **`search_audit`** — `audit_id, event_ts, user_email, query, search_mode, filters, num_results, result_doc_ids (array), top_snippet, latency_ms, app_session`.

### Chunking
One chunk per **page** (≈7 chunks/doc, ~140 total). Page-level chunking is ideal here because (a) it gives a precise **page reference** to show the analyst, and (b) ISDA clauses are self-contained enough that a page is a coherent retrieval unit. Larger corpora would move to ~500-token sliding windows.

---

## 4. Search & ranking logic (in the app)

1. **Normalize** the query; detect multi-word phrases vs terms.
2. **Lane 1 — Exact:** `SELECT ... FROM document_chunks WHERE lower(chunk_text) LIKE '%'||lower(:q)||'%'` (or `rlike` for regex/boolean). Returns every matching chunk — **complete**. Optional metadata filters (governing law, counterparty, product) apply as SQL `WHERE`.
3. **Lane 2 — Semantic:** `index.similarity_search(query_text=q, columns=[...], query_type="HYBRID", num_results=50)`, with the same optional filters passed as VS filters.
4. **Merge:** union chunk hits, tag each `match_type ∈ {exact, semantic, both}`, group by `doc_id`.
5. **Rank:** documents with an exact hit first (recall-first ordering), then by best semantic score; within a doc, order snippets by page.
6. **Present:** per document — counterparty, governing law, effective date; then each matching snippet with the **keyword highlighted** and its **page number**. Badge shows how the match was found.
7. **Audit:** write one `search_audit` row (user email from the app's `X-Forwarded-Email` / `X-Forwarded-Preferred-Username` header, timestamp, query, mode, filters, count, returned doc_ids, latency).

---

## 5. Accuracy & validation strategy
- **Golden keyword set** (built into `deploy/validate_search.py`): e.g. `Automatic Early Termination` (expected: only AET-applies docs), `Bail-in` (EEA/UK banks), `Credit Default Swaps` (product subset), each counterparty name, a specific LEI, `USD 50,000,000`. For every golden term we assert the exact lane returns **exactly** the documents known to contain it (from the generator's manifest). This is a regression test that the recall guarantee holds.
- **Zero-miss check:** because Lane 1 is an exhaustive `LIKE`, recall on exact terms is provably 100% for the corpus; the golden test makes that continuously verifiable.

---

## 6. Governance, security, audit
- Everything lives in **Unity Catalog** (`isda_search.isda`) — table/volume ACLs, lineage, and audit apply.
- The **App service principal** gets `USE CATALOG/SCHEMA`, `SELECT` on the tables, `READ VOLUME`, `CAN_QUERY` on the vector index, and **`MODIFY`/`INSERT` on `search_audit`** only.
- The **who/when/what/result** history is the `search_audit` table — durable, queryable, and separable from Databricks system audit logs. A History tab in the app surfaces it.

## 7. Deliverables / build order
1. `deploy/01_setup_uc.py` — catalog (or schema fallback) + schema + volume; upload 20 PDFs. ✅ scripted
2. `deploy/02_ingest.py` — parse PDFs → `documents` + `document_chunks` (CDF on).
3. `deploy/03_vector_search.py` — endpoint + Delta Sync hybrid index; wait ONLINE.
4. `deploy/04_audit.py` — `search_audit` table.
5. `deploy/validate_search.py` — golden-keyword recall regression.
6. `app/` — Streamlit Databricks App (exact + semantic + hybrid, highlight, page refs, history).

## 8. Scaling notes (beyond the demo)
- 20 → 10k docs: keep both lanes; move chunking to token windows; the exact lane stays exhaustive until it doesn't (then add a DBSQL full-text/`ai_query` pre-filter or an external BM25 engine — Option E).
- Add `ai_parse_document` for scanned PDFs and `ai_query` clause classification to enrich `documents` metadata for richer filters.
