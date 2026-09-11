# ISDA Search — Enhancement Plan (v2, for review)

**Date:** 2026-09-11 · **Status:** proposal — *no code will change until you approve a scope.*
**Inputs:** iManage blog (AI extraction of ISDA/CSA data), ISDA May-2025 GenAI paper (extracting & digitizing CSA clauses), Sirion/Eigen "ISDA documentation process" (UI/workflow blueprint — page blocked automated fetch, reconstructed via research).

---

## 1. What the three sources tell us

**iManage — "ISDA derivative contract data extraction using AI"**
- Banks manually key negotiated terms from ISDA Masters & CSAs into collateral systems — error-prone, slow, needs ~100% accuracy (counterparty credit risk + regulatory).
- AI reads → interprets → extracts → summarizes; converts **unstructured → structured**.
- Valuable capabilities: **audit** extracted-vs-manual, **batch portfolio analysis** for risk relationships, **metadata mapping** to downstream systems, **repapering scope** identification.

**ISDA — "Generative AI to extract & digitize CSA clauses" (May 2025)**
- Evaluated **8 LLMs** extracting **5 key CSA clauses**; named ones: **Base/Eligible Currency, Minimum Transfer Amount, Threshold** (varying linguistic complexity).
- Accuracy **>90%** with domain context; **100%** on simple clauses; complex clauses need help.
- Big levers: **few-shot prompting + the ISDA Documentation Taxonomy + ISDA Clause Library**.
- Output is **digitized into the Common Domain Model (CDM)** — a machine-readable schema enabling straight-through processing.

**Sirion/Eigen — "ISDA documentation process" (UI/workflow blueprint)**
- Import → **auto-extract** → **prioritized review dashboard** (low-confidence / high-risk flags) → **clause review pane** (doc viewer + extracted fields + canonical-clause recommendation) → **library mapping** → **comparison/redline** → **obligations register/calendar** → **approve & export (JSON/CSV/API)** → **model-retrain loop**.
- Cross-cutting: **confidence scores + provenance** (highlight source sentence + page), **HITL accept/edit**, **roles** (legal / collateral ops / PM / admin), **rule-based validation** (missing mandatory field, numeric anomaly), **audit trail**.

### The through-line
All three point the same way: **move from "find the document" to "extract, structure, validate, and act on the clauses inside it."** Our app already nails *find* (exact + semantic + hybrid + full-text). The enhancements add *extract → digitize → audit → analyze → answer*, with confidence + provenance + human-in-the-loop — exactly the ISDA/iManage/Sirion pattern, built natively on Databricks.

---

## 2. Where our app is today
Search (Exact/Semantic/Hybrid) · Full-text BM25 (Option B) · Compare A vs B · Documents · History (audit) · Architecture. Data: `documents` (20 + full_text), `document_chunks` (132, PK+CDF), `search_audit`; a vector index + a full-text index. It finds documents and shows highlighted snippets + pages.

---

## 3. Proposed enhancements (prioritized)

### P0 — Fix the "Open document" link *(bug from last change)*
The `…/explore/data/volumes/…/<file>.pdf` deep-link 404s (that UI route lists a folder, it doesn't open a file). **Fix:** serve the PDF from the app — a `📄 Open / download PDF` control that streams the bytes from the Volume via the Files API (the app SP already has `READ VOLUME`). Reliable, opens the real PDF. *Small.*

### P1 — AI Clause Extraction  → new **🧬 Extract** tab  *(the centerpiece; mirrors ISDA paper + iManage)*
Use a Databricks Foundation Model to read each agreement and extract the **negotiated clause register** into structured data, with **value + source snippet + page + confidence** per field — the ISDA-paper pattern, generalized beyond the 5 CSA clauses.
- **Fields (Master + CSA):** Party A/B, LEI, Governing Law, Effective Date, Base Currency, Eligible Currency, Eligible Collateral, **Threshold (per party)**, **Minimum Transfer Amount**, **Independent Amount**, Rounding, Valuation Agent, Notification/Valuation Time, Interest rate on cash, **Automatic Early Termination (applies?)**, **Cross-Default Threshold Amount**, Specified Entity, Additional Termination Events, Set-off, Bail-in recognition.
- **How (Databricks):** `ai_query('databricks-claude-sonnet-4-6', …, responseFormat=json_schema)` run in SQL over `documents.full_text` (batch), returning a strict JSON object per doc → new table **`clause_extractions`** (`doc_id, clause_name, value, page, snippet, confidence, model, extracted_at`). Prompt seeded with **clause definitions** (our stand-in for the ISDA Taxonomy/Clause Library) + few-shot examples — the paper's biggest accuracy lever.
- **UI:** per-document clause register (field · value · confidence badge · "source" popover showing the snippet + page · Open PDF); a **"Digitize"** JSON export (CDM-inspired schema).

### P2 — Extraction accuracy / audit  → panel in **🧬 Extract**  *(mirrors iManage audit + ISDA accuracy focus)*
We have ground truth (the generator manifest). Compare **LLM-extracted vs golden** per clause → **accuracy % per clause**, overall score, and a flagged **mismatch list**. Demonstrates the "needs ~100% accuracy / validate against manual" requirement and quantifies model quality (the paper's core result).

### P3 — Portfolio analytics  → new **📊 Portfolio** tab  *(mirrors iManage batch/risk + Sirion dashboard)*
Aggregate across all 20 agreements: governing-law split, base-currency mix, # with AET, cross-default threshold distribution, **ATE-trigger frequency** (NAV-decline / ratings-downgrade / bail-in / key-person), and a simple **risk-indicator score** per counterparty (e.g., downgrade triggers + high thresholds). Charts via the `dataviz` design system.

### P4 — Clause comparison across counterparties  → **📊 Portfolio** sub-view  *(mirrors Sirion comparison/redline + clause library)*
Pick a clause (Threshold, MTA, AET, Governing Law, …) → side-by-side value across selected counterparties, deltas highlighted against a chosen baseline/template. Turns the clause register into a negotiation-benchmarking tool.

### P5 — Grounded portfolio Q&A  → new **💬 Ask** tab  *(the GenAI headline capability)*
Natural-language questions over the corpus: retrieve top chunks (our hybrid vector index) → `chat.completions` grounded answer **with citations (doc + page)**. e.g. *"Which counterparties have Automatic Early Termination?"*, *"List agreements with an NAV-decline trigger tighter than 20%."* (Client-side RAG; `chat.completions` passthrough is the supported path in this workspace.)

### P6 — Human-in-the-loop review  → in **🧬 Extract**  *(mirrors Sirion review + our audit pattern)*
`st.data_editor` lets a reviewer **confirm/edit** each extracted value; status (pending/approved/edited) + reviewer + timestamp written back to `clause_extractions`. Produces an **approved clause register** and extends our who/when/what audit trail to extractions.

### P7 — Stretch / future
Obligations register + calendar (margin-call dates, notice periods); CDM-conformant JSON export + REST push to a collateral system; editable clause library/taxonomy; **repapering flags** (missing bail-in, stale effective dates); model-retrain feedback loop.

---

## 4. Suggested first slice (my recommendation)
**P0 + P1 + P2 + P3.** This delivers the on-message core — *extract → digitize → validate → analyze* — end to end and demoable, reusing all existing infra (warehouse, tables, app, SP). P4/P5/P6 land next; P7 is future.

New assets this slice adds: table `clause_extractions`; deploy scripts `07_extract_clauses.py` (+ golden compare) ; app tabs **🧬 Extract** and **📊 Portfolio**; the P0 PDF-serving fix. Grants: app SP already covers reads; add `CAN QUERY` on the `databricks-claude-sonnet-4-6` FM endpoint if needed and SELECT/MODIFY on `clause_extractions`.

---

## 5. Decisions I'd like from you
1. **Scope** — do the recommended **P0–P3** first, or a different set (e.g., add P5 "Ask" for the flashiest demo)?
2. **Extraction model** — default **`databricks-claude-sonnet-4-6`** (works via `ai_query`/chat.completions here). OK?
3. **HITL review (P6)** — include now or defer?
4. **Accuracy bar** — surface per-clause confidence + accuracy-vs-golden (recommended, matches the paper), yes?

Once you pick, I'll implement, deploy to the same app, and verify in-browser as before.
