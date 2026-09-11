"""ISDA Contract Search — Databricks App for Legal Analysts.

Two-lane search:
  - Exact (lexical): SQL ILIKE over document_chunks. 100% recall on exact terms.
  - Semantic: Mosaic AI Vector Search index in HYBRID mode.
  - Hybrid (default): both, merged and de-duplicated by document.

Results show the matching snippets with the keyword highlighted and the page
reference. Every search is written to the audit table (who / when / what /
result), surfaced in the History tab.
"""
import html
import base64
import json
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from databricks.sdk import WorkspaceClient

import cdm
import config

st.set_page_config(page_title="ISDA Contract Search", page_icon="📄",
                   layout="wide")

WAREHOUSE = config.get("warehouse_id")
DOCS_TBL = config.get("documents_table")
CHUNKS_TBL = config.get("chunks_table")
AUDIT_TBL = config.get("audit_table")
VS_ENDPOINT = config.get("vs_endpoint")
VS_INDEX = config.get("vs_index")
FTS_ENDPOINT = config.get("fts_endpoint")
FTS_INDEX = config.get("fts_index")
EXTRACTIONS_TBL = config.get("extractions_table")
COLLATERAL_TBL = config.get("collateral_table")
LLM_MODEL = config.get("llm_model")


@st.cache_resource
def ws():
    return WorkspaceClient()


def run_sql(statement):
    w = ws()
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE, statement=statement, wait_timeout="50s")
    while resp.status and resp.status.state and resp.status.state.value in (
            "PENDING", "RUNNING"):
        time.sleep(1)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if not (resp.status and resp.status.state
            and resp.status.state.value == "SUCCEEDED"):
        err = (resp.status.error.message if resp.status and resp.status.error
               else "unknown")
        raise RuntimeError("SQL failed: %s" % err)
    cols = ([c.name for c in resp.manifest.schema.columns]
            if resp.manifest and resp.manifest.schema else [])
    out = []
    if resp.result and resp.result.data_array:
        for r in resp.result.data_array:
            out.append(dict(zip(cols, r)))
    return out


@st.cache_data(ttl=300)
def load_documents():
    rows = run_sql("""
        SELECT doc_id, file_name, counterparty, counterparty_short,
               counterparty_type, jurisdiction, lei, governing_law, base_currency,
               threshold, minimum_transfer_amount, independent_amount,
               cross_default_threshold, automatic_early_termination, csa_type,
               products, specified_entity, additional_termination_events,
               CAST(effective_date AS STRING) effective_date, page_count
        FROM %s ORDER BY doc_id""" % DOCS_TBL)
    return {r["doc_id"]: r for r in rows}


@st.cache_resource
def _vsc():
    from databricks.vector_search.client import VectorSearchClient
    w = ws()
    token = w.config.authenticate()["Authorization"].split(" ", 1)[1]
    return VectorSearchClient(workspace_url=w.config.host,
                              personal_access_token=token, disable_notice=True)


@st.cache_resource
def vs_index():
    return _vsc().get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)


@st.cache_resource
def fts_index():
    """Option B: full-text (BM25) index on the storage-optimized endpoint.
    Raises if the workspace 'Full Text' preview isn't enabled / index absent."""
    return _vsc().get_index(endpoint_name=FTS_ENDPOINT, index_name=FTS_INDEX)


def user_email():
    try:
        h = st.context.headers
        return (h.get("X-Forwarded-Email") or h.get("X-Forwarded-Preferred-Username")
                or h.get("X-Forwarded-User") or "unknown")
    except Exception:
        return "unknown"


@st.cache_data(ttl=3600, show_spinner=False)
def pdf_bytes(file_name):
    """Fetch the PDF from the UC Volume via the Files API (app SP has READ
    VOLUME). Cached per session so expanders don't re-fetch."""
    path = "/Volumes/%s/%s/contracts/contracts/%s" % (
        config.get("catalog"), config.get("schema"), file_name)
    return ws().files.download(path).contents.read()


def render_open_pdf(file_name, key):
    """Reliable 'open the document' — serves the actual PDF bytes (the workspace
    /explore deep-link 404s for a single file, and Files API URLs need a bearer
    token, so a plain link can't work; a served download does)."""
    try:
        st.download_button("📄 Open / download PDF", data=pdf_bytes(file_name),
                           file_name=file_name, mime="application/pdf", key=key)
    except Exception as e:
        st.caption("PDF unavailable (%s)" % str(e)[:80])


@st.cache_data(ttl=3600, show_spinner=False)
def pdf_page_images(file_name, zoom=1.6):
    """Rasterize each PDF page to PNG bytes (Chrome blocks data:/blob: PDFs in
    the app's sandboxed iframe, so we render server-side and show images)."""
    import pymupdf
    d = pymupdf.open(stream=pdf_bytes(file_name), filetype="pdf")
    return [d[i].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
            for i in range(d.page_count)]


def render_pdf_inline(file_name):
    """Open the PDF *inside the app* — page images rendered server-side."""
    try:
        imgs = pdf_page_images(file_name)
        for i, png in enumerate(imgs, 1):
            st.image(png, caption="Page %d of %d" % (i, len(imgs)),
                     use_container_width=True)
    except Exception as e:
        st.caption("In-app preview unavailable (%s). Use Download instead."
                   % str(e)[:100])


def doc_open_controls(doc_meta, key_prefix):
    """Both ways to open a document: download, and in-app page-image preview."""
    fn = doc_meta.get("file_name")
    if not fn:
        st.caption("No file for this document.")
        return
    st.markdown("**%s — %s**" % (doc_meta.get("doc_id", ""),
                                 doc_meta.get("counterparty", "")))
    c1, c2 = st.columns([1, 2])
    with c1:
        render_open_pdf(fn, key="%s_dl" % key_prefix)
    with c2:
        open_in_app = st.toggle("📖 Open in app (page preview)",
                                key="%s_toggle" % key_prefix)
    if open_in_app:
        render_pdf_inline(fn)


@st.dialog("CDM-aligned document", width="large")
def cdm_view_dialog(cdm_doc, ok, errs):
    if ok:
        st.success("✅ Valid against the CDM-aligned JSON Schema "
                   "(LegalAgreement · CreditSupportAgreementElections · "
                   "MasterAgreementElections).")
    else:
        st.error("Schema validation failed:\n- " + "\n- ".join(errs))
    st.caption("Validated with jsonschema against this app's CDM-aligned schema. "
               "Full FINOS release-schema binding needs the CDM distribution "
               "artifacts. Confidence + page provenance travel in `meta`.")
    st.json(cdm_doc)


@st.dialog("Clause → CDM mapping", width="large")
def cdm_map_dialog():
    st.dataframe(
        [{"Extracted clause": c, "CDM path": p} for c, p in cdm.CDM_MAP],
        use_container_width=True, hide_index=True)


# --------------------------- search lanes ---------------------------------
def build_filter_sql(filters):
    clauses = []
    if filters.get("governing_law"):
        vals = ",".join("'%s'" % v for v in filters["governing_law"])
        clauses.append("d.governing_law IN (%s)" % vals)
    if filters.get("counterparty_type"):
        vals = ",".join("'%s'" % v for v in filters["counterparty_type"])
        clauses.append("d.counterparty_type IN (%s)" % vals)
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def exact_search(query, filters, limit=200):
    q = query.replace("'", "''")
    sql = """
        SELECT c.doc_id, c.page, c.chunk_text
        FROM {chunks} c JOIN {docs} d ON c.doc_id = d.doc_id
        WHERE lower(c.chunk_text) LIKE lower('%{q}%') {flt}
        ORDER BY c.doc_id, c.page LIMIT {lim}
    """.format(chunks=CHUNKS_TBL, docs=DOCS_TBL, q=q,
               flt=build_filter_sql(filters), lim=limit)
    return run_sql(sql)


def semantic_search(query, filters, query_type="ANN", num_results=40):
    """Vector Search lane.
    query_type="ANN"    -> pure vector nearest-neighbour (Semantic mode).
    query_type="HYBRID" -> vector + keyword (BM25) rank-fused (Hybrid mode)."""
    idx = vs_index()
    # NOTE: filters are applied in the app after retrieval for robustness; we
    # always request the doc columns so we can group + highlight.
    res = idx.similarity_search(
        query_text=query,
        columns=["chunk_id", "doc_id", "page", "chunk_text"],
        num_results=num_results, query_type=query_type)
    data = (res.get("result", {}) or {}).get("data_array", []) or []
    cols = [c["name"] for c in
            (res.get("manifest", {}) or {}).get("columns", [])] or \
           ["chunk_id", "doc_id", "page", "chunk_text", "score"]
    rows = [dict(zip(cols, r)) for r in data]
    return rows


def fulltext_search(query, num_results=200):
    """Option B keyword lane: Databricks-managed BM25 full-text index
    (query_type='FULL_TEXT') on the storage-optimized endpoint."""
    idx = fts_index()
    res = idx.similarity_search(
        query_text=query,
        columns=["chunk_id", "doc_id", "page", "chunk_text"],
        num_results=num_results, query_type="FULL_TEXT")
    data = (res.get("result", {}) or {}).get("data_array", []) or []
    cols = [c["name"] for c in
            (res.get("manifest", {}) or {}).get("columns", [])] or \
           ["chunk_id", "doc_id", "page", "chunk_text", "score"]
    return [dict(zip(cols, r)) for r in data]


# ---------------------- clause extraction (P1/P2/P6) ----------------------
@st.cache_data(ttl=120)
def load_extractions():
    try:
        return run_sql("""
            SELECT doc_id, clause_name, value, page, snippet,
                   round(confidence,2) AS confidence, status, reviewed_value,
                   reviewed_by, CAST(reviewed_at AS STRING) AS reviewed_at
            FROM %s ORDER BY doc_id, clause_name""" % EXTRACTIONS_TBL)
    except Exception:
        return []


@st.cache_data(ttl=120)
def load_collateral():
    try:
        return run_sql("""
            SELECT doc_id, asset_type, issuer, maturity_band,
                   valuation_percentage, haircut_percentage, currency
            FROM %s""" % COLLATERAL_TBL)
    except Exception:
        return []


# Map extracted clause_name -> the golden column in `documents` (ground truth).
GOLDEN_MAP = {
    "Counterparty (Party B)": "counterparty",
    "Counterparty LEI": "lei",
    "Governing Law": "governing_law",
    "Base Currency": "base_currency",
    "Threshold": "threshold",
    "Minimum Transfer Amount": "minimum_transfer_amount",
    "Independent Amount": "independent_amount",
    "Cross-Default Threshold Amount": "cross_default_threshold",
    "Specified Entity": "specified_entity",
    "Automatic Early Termination": "automatic_early_termination",
    "Effective Date": "effective_date",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _date_key(s):
    """Parse ISO 'YYYY-MM-DD' or 'DD Month YYYY' into a (y, m, d) tuple."""
    s = str(s).strip().lower()
    iso = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        return tuple(int(g) for g in iso.groups())
    yr = re.search(r"(19|20)\d\d", s)
    day = re.search(r"\b(\d{1,2})\b", s)
    mo = next((n for name, n in _MONTHS.items() if name in s), None)
    if yr and mo and day:
        return (int(yr.group(0)), mo, int(day.group(1)))
    return None


def golden_match(clause_name, extracted, golden):
    """Lenient correctness check of an extracted value vs the golden value.
    Returns None when there is no golden value to compare against."""
    if golden is None or str(golden).strip() in ("", "None"):
        return None
    if clause_name == "Effective Date":
        ek, gk = _date_key(extracted), _date_key(golden)
        return (ek == gk) if (ek and gk) else None
    if clause_name == "Automatic Early Termination":
        applies = str(golden).lower() in ("true", "1")
        ev = str(extracted).lower()
        said_applies = ("appl" in ev and not ev.strip().startswith("not")
                        and "will not apply to either" not in ev
                        and "does not apply to either" not in ev)
        return applies == said_applies
    g, e = _norm(golden), _norm(extracted)
    if not g:
        return None            # no golden to compare
    return g in e or e in g


def ask_llm(question):
    """Grounded Q&A (P5): compact structured portfolio context + retrieved
    snippets -> ai_query. Returns (answer, retrieved_hits)."""
    docs = load_documents()
    lines = []
    for d in docs.values():
        ate = d.get("additional_termination_events")
        lines.append("[%s] %s | law=%s | base_ccy=%s | AET=%s | cross_default=%s "
                     "| CSA=%s | ATEs=%s"
                     % (d["doc_id"], d["counterparty"], d["governing_law"],
                        d["base_currency"], d["automatic_early_termination"],
                        d["cross_default_threshold"], d.get("csa_type", ""), ate))
    portfolio = "\n".join(lines)
    try:
        hits = semantic_search(question, {}, query_type="HYBRID", num_results=6)
    except Exception:
        hits = []
    snips = "\n\n".join("[%s p.%s] %s" % (h.get("doc_id"), h.get("page"),
                        str(h.get("chunk_text", ""))[:600]) for h in hits)
    prompt = ("You are an ISDA portfolio analyst. Answer the QUESTION using ONLY "
              "the data below (a summary of all 20 agreements, plus retrieved "
              "excerpts). Cite the agreements you rely on as [doc_id]. If the "
              "answer is not in the data, say so.\n\nPORTFOLIO SUMMARY:\n%s\n\n"
              "RETRIEVED EXCERPTS:\n%s\n\nQUESTION: %s"
              % (portfolio, snips, question)).replace("'", "''")
    ans = run_sql("SELECT ai_query('%s', '%s') AS a" % (LLM_MODEL, prompt))
    return (ans[0]["a"] if ans else "(no answer)"), hits



def highlight(text, query, window=320):
    """Return an HTML snippet around the first match with the term marked.
    Escapes the raw text first, then wraps matches in <mark> on the escaped
    string so no user content can inject markup."""
    if not query:
        return html.escape(text[:window])
    i = text.lower().find(query.lower())
    if i < 0:
        seg = text[:window]
        return html.escape(seg) + ("…" if len(text) > window else "")
    start = max(0, i - window // 2)
    end = min(len(text), i + len(query) + window // 2)
    esc = html.escape(text[start:end])
    pat = re.compile(re.escape(html.escape(query)), re.IGNORECASE)
    esc = pat.sub(lambda m: "<mark>%s</mark>" % m.group(0), esc)
    pre = "…" if start > 0 else ""
    post = "…" if end < len(text) else ""
    return pre + esc + post


def do_search(query, mode, filters):
    docs = load_documents()
    merged = {}   # doc_id -> {meta, snippets:[{page,text,match_type}], score}

    def add(doc_id, page, text, mtype, score=0.0):
        if doc_id not in docs:
            return
        m = merged.setdefault(doc_id, {"meta": docs[doc_id], "snippets": [],
                                       "score": 0.0, "types": set()})
        m["snippets"].append({"page": page, "text": text, "match_type": mtype})
        m["score"] = max(m["score"], score)
        m["types"].add(mtype)

    # Exact lane: runs in Exact mode and as the 100%-recall floor of Hybrid.
    if mode in ("Exact", "Hybrid"):
        for r in exact_search(query, filters):
            add(r["doc_id"], int(r["page"]), r["chunk_text"], "exact", 1.0)
    # Vector Search lane: pure ANN for Semantic, HYBRID (vector+keyword) for Hybrid.
    if mode in ("Semantic", "Hybrid"):
        qtype = "ANN" if mode == "Semantic" else "HYBRID"
        try:
            for r in semantic_search(query, filters, query_type=qtype):
                sc = float(r.get("score", 0) or 0)
                add(r["doc_id"], int(r.get("page", 0) or 0),
                    r.get("chunk_text", ""), "semantic", sc)
        except Exception as e:
            import traceback
            print("SEMANTIC_LANE_ERROR:\n" + traceback.format_exc(), flush=True)
            note = ("Showing exact matches." if mode == "Hybrid"
                    else "Try Exact or Hybrid mode.")
            st.warning("Semantic lane unavailable (%s). %s" % (str(e)[:200], note))

    # de-dupe snippets per doc by page, prefer exact
    for m in merged.values():
        seen, uniq = {}, []
        for s in sorted(m["snippets"], key=lambda x: (x["match_type"] != "exact",
                                                      x["page"])):
            if s["page"] in seen:
                continue
            seen[s["page"]] = True
            uniq.append(s)
        m["snippets"] = uniq
        m["match_label"] = ("both" if {"exact", "semantic"} <= m["types"]
                            else next(iter(m["types"])))
    # rank: exact-first, then score
    ordered = sorted(merged.items(),
                     key=lambda kv: (0 if "exact" in kv[1]["types"] else 1,
                                     -kv[1]["score"], kv[0]))
    return ordered


def do_fulltext(query, filters):
    """Method B: full-text BM25 index. Returns the same shape as do_search so
    the results render identically."""
    docs = load_documents()
    merged = {}
    for r in fulltext_search(query):
        d = r["doc_id"]
        meta = docs.get(d)
        if not meta:
            continue
        if (filters.get("governing_law") and
                meta["governing_law"] not in filters["governing_law"]):
            continue
        if (filters.get("counterparty_type") and
                meta["counterparty_type"] not in filters["counterparty_type"]):
            continue
        m = merged.setdefault(d, {"meta": meta, "snippets": [], "score": 0.0,
                                  "types": {"fulltext"}})
        m["snippets"].append({"page": int(r.get("page", 0) or 0),
                              "text": r.get("chunk_text", ""),
                              "match_type": "fulltext"})
        m["score"] = max(m["score"], float(r.get("score", 0) or 0))
    for m in merged.values():
        seen, uniq = set(), []
        for s in sorted(m["snippets"], key=lambda x: x["page"]):
            if s["page"] in seen:
                continue
            seen.add(s["page"])
            uniq.append(s)
        m["snippets"] = uniq
        m["match_label"] = "fulltext"
    return sorted(merged.items(), key=lambda kv: -kv[1]["score"])


def write_audit(query, mode, filters, ordered, latency_ms):
    doc_ids = [d for d, _ in ordered]
    arr = "array(%s)" % ",".join("'%s'" % d for d in doc_ids) if doc_ids \
        else "array()"
    top = ""
    if ordered and ordered[0][1]["snippets"]:
        top = ordered[0][1]["snippets"][0]["text"][:300]
    vals = dict(
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        user=user_email().replace("'", "''"),
        q=query.replace("'", "''"),
        mode=mode,
        flt=json.dumps(filters).replace("'", "''"),
        n=len(doc_ids),
        top=top.replace("'", "''"),
        lat=int(latency_ms),
        sess=st.session_state.get("sid", "").replace("'", "''"),
    )
    run_sql("""
        INSERT INTO {tbl} (audit_id, event_ts, user_email, query, search_mode,
            filters, num_results, result_doc_ids, top_snippet, latency_ms, app_session)
        VALUES ('{id}', TIMESTAMP'{ts}', '{user}', '{q}', '{mode}', '{flt}',
                {n}, {arr}, '{top}', {lat}, '{sess}')
    """.format(tbl=AUDIT_TBL, arr=arr, **vals))


# ------------------------------- UI ---------------------------------------
if "sid" not in st.session_state:
    st.session_state["sid"] = uuid.uuid4().hex[:12]

st.title("📄 ISDA Contract Search")
st.caption("Search ISDA master agreements by keyword — exact recall guaranteed, "
           "with semantic recall on top. Signed in as **%s**." % user_email())

(tab_portfolio, tab_docs, tab_extract, tab_search, tab_ask,
 tab_history, tab_arch) = st.tabs(
    ["📊 Portfolio", "📚 Documents", "🧬 Extract", "🔎 Search", "💬 Ask",
     "🕑 History", "🏗️ Architecture"])

with tab_search:
    docs = load_documents()
    laws = sorted({d["governing_law"] for d in docs.values()})
    types = sorted({d["counterparty_type"] for d in docs.values()})

    query = st.text_input("Keyword or phrase",
                          placeholder="e.g. Automatic Early Termination, "
                                      "Credit Default Swaps, Goldman Sachs, "
                                      "Net Asset Value Decline")
    e1, e2 = st.columns(2)
    with e1:
        engine = st.radio(
            "Method", ["A · Vector search", "B · Full-text index (BM25)"],
            help="A: embedding-based Vector Search (+ direct keyword). "
                 "B: Databricks-managed BM25 full-text index.")
    with e2:
        if engine.startswith("A"):
            submode = st.radio(
                "A mode", ["Hybrid", "Semantic", "Direct"],
                help="Hybrid (default) = Direct keyword ∪ Vector HYBRID "
                     "(vector+keyword). Semantic = pure vector ANN (meaning). "
                     "Direct = exact keyword match (SQL ILIKE, 100% recall).")
        else:
            submode = None
            st.caption("BM25 keyword relevance ranking on the storage-optimized "
                       "index.")
    f1, f2 = st.columns(2)
    with f1:
        gl = st.multiselect("Governing law", laws)
    with f2:
        ct = st.multiselect("Counterparty type", types)
    filters = {"governing_law": gl, "counterparty_type": ct}

    if st.button("Search", type="primary") and query.strip():
        q = query.strip()
        t0 = time.time()
        if engine.startswith("A"):
            mode = {"Hybrid": "Hybrid", "Semantic": "Semantic",
                    "Direct": "Exact"}[submode]
            label = "A · %s" % submode
            ordered = do_search(q, mode, filters)
        else:
            label = "B · Full-text (BM25)"
            try:
                ordered = do_fulltext(q, filters)
            except Exception as e:
                msg = str(e)
                if "Full Text is not yet enabled" in msg or "not exist" in msg:
                    st.warning("Method B (full-text index) isn't active — enable "
                               "the workspace Full Text preview and build the "
                               "index. Use Method A meanwhile.")
                else:
                    st.error("Full-text search error: %s" % msg[:200])
                ordered = []
        latency = (time.time() - t0) * 1000
        try:
            write_audit(q, label, filters, ordered, latency)
        except Exception as e:
            st.info("(audit write skipped: %s)" % str(e)[:100])

        st.subheader("%d document%s matched · %s · %d ms"
                     % (len(ordered), "" if len(ordered) == 1 else "s", label,
                        int(latency)))
        badge_map = {"exact": "🟢 direct", "semantic": "🔵 semantic",
                     "both": "🟢🔵 direct+semantic", "fulltext": "🟣 BM25"}
        tag_map = {"exact": "🟢", "semantic": "🔵", "fulltext": "🟣"}
        for doc_id, m in ordered:
            meta = m["meta"]
            badge = badge_map.get(m["match_label"], "")
            with st.expander("**%s** — %s   ·   %s law · %s · %s   [%s]"
                             % (meta["counterparty"], meta["file_name"],
                                meta["governing_law"], meta["base_currency"],
                                meta["counterparty_type"], badge), expanded=True):
                st.markdown("LEI `%s` · Effective %s · CSA: %s · Cross-default: %s"
                            % (meta["lei"], meta["effective_date"], meta["csa_type"],
                               meta["cross_default_threshold"]))
                for s in m["snippets"][:6]:
                    tag = tag_map.get(s["match_type"], "")
                    st.markdown(
                        "%s **p.%d** — %s" % (tag, s["page"],
                                              highlight(s["text"], q)),
                        unsafe_allow_html=True)
                render_open_pdf(meta["file_name"], key="pdf_search_%s" % doc_id)
        if not ordered:
            st.info("No documents matched.")

with tab_docs:
    docs = load_documents()
    st.subheader("Contract library — %d ISDA agreements" % len(docs))
    doc_list = list(docs.values())
    st.dataframe(
        [{"Doc": d["doc_id"], "Counterparty": d["counterparty"],
          "Type": d["counterparty_type"], "Gov. law": d["governing_law"],
          "Base ccy": d["base_currency"], "AET": d["automatic_early_termination"],
          "CSA": d["csa_type"], "Effective": d["effective_date"],
          "Pages": d["page_count"]}
         for d in doc_list],
        use_container_width=True, hide_index=True)
    st.markdown("**Open a document**")
    opts = ["—"] + ["%s — %s" % (d["doc_id"], d["counterparty"])
                    for d in doc_list]
    pick = st.selectbox("Choose an agreement", opts, key="docs_open",
                        label_visibility="collapsed")
    if pick != "—":
        doc_open_controls(doc_list[opts.index(pick) - 1], key_prefix="docs")


def _coerce_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            return json.loads(v)
        except Exception:
            return [v]
    return [v] if v else []


with tab_extract:
    docs = load_documents()
    ex = load_extractions()
    st.subheader("🧬 AI clause extraction & digitization")
    if not ex:
        st.info("No extractions yet — run `deploy/07_extract_clauses.py` to "
                "populate the clause register.")
    else:
        st.caption("Select an agreement to see its clauses extracted by **%s** "
                   "into the schema derived from the FINOS CDM legal-agreement "
                   "model." % LLM_MODEL)
        ids = sorted({r["doc_id"] for r in ex})
        sel = st.selectbox("Agreement", ids,
                           format_func=lambda d: "%s — %s"
                           % (d, docs.get(d, {}).get("counterparty", d)))
        rows = [r for r in ex if r["doc_id"] == sel]
        st.dataframe(
            [{"Clause": r["clause_name"], "Extracted value": r["value"],
              "Page": r["page"], "Snippet": r["snippet"]} for r in rows],
            use_container_width=True, hide_index=True,
            column_config={"Snippet": st.column_config.TextColumn(
                "Snippet", width="large")})
        render_open_pdf(docs.get(sel, {}).get("file_name", ""),
                        key="pdf_ex_%s" % sel)

        # CDM digitization is an IT/technical output — kept compact as icons
        # that open popups, so the analyst view stays clean.
        cdm_doc = cdm.build_cdm(sel, rows, load_collateral(), model=LLM_MODEL)
        ok, errs = cdm.validate_cdm(cdm_doc)
        st.caption("Digitize → FINOS CDM (technical / IT outputs)")
        i1, i2, i3, i4 = st.columns(4)
        with i1:
            if st.button("🧬 View CDM", key="cdmview_%s" % sel,
                         use_container_width=True,
                         help="CDM-aligned JSON + schema validation (popup)"):
                cdm_view_dialog(cdm_doc, ok, errs)
        with i2:
            if st.button("🗺️ CDM mapping", key="cdmmap_%s" % sel,
                         use_container_width=True,
                         help="Clause → CDM path mapping (popup)"):
                cdm_map_dialog()
        with i3:
            st.download_button("⬇️ CDM JSON", data=json.dumps(cdm_doc, indent=2),
                               file_name="%s_cdm.json" % sel,
                               mime="application/json", key="cdm_%s" % sel,
                               use_container_width=True)
        with i4:
            st.download_button("⬇️ Raw register",
                               data=json.dumps(rows, indent=2, default=str),
                               file_name="%s_clauses.json" % sel,
                               mime="application/json", key="dig_%s" % sel,
                               use_container_width=True)

        st.divider()
        st.markdown("### Clause comparison across counterparties")
        clause_names = sorted({r["clause_name"] for r in ex})
        default_ix = (clause_names.index("Threshold")
                      if "Threshold" in clause_names else 0)
        clause = st.selectbox("Clause", clause_names, index=default_ix,
                              key="cmp_clause")
        comp = [{"Doc": r["doc_id"],
                 "Counterparty": docs.get(r["doc_id"], {}).get(
                     "counterparty", r["doc_id"]),
                 "Value": r["value"], "Page": r["page"],
                 "Snippet": r["snippet"]}
                for r in ex if r["clause_name"] == clause]
        comp.sort(key=lambda x: x["Counterparty"])
        st.dataframe(comp, use_container_width=True, hide_index=True,
                     column_config={"Snippet": st.column_config.TextColumn(
                         "Snippet", width="large")})


def clickable_bar(counts, title, key):
    """Altair bar chart with a click selection (st.altair_chart supports
    on_select; st.bar_chart does not). Streamlit 1.63 ships a matching Vega
    runtime, so the earlier version-mismatch projection error is gone. Returns
    the clicked categories; click a bar to select, empty space to clear."""
    df = pd.DataFrame({"cat": list(counts.keys()),
                       "Agreements": list(counts.values())})
    sel = alt.selection_point(fields=["cat"], name="pts")
    chart = (alt.Chart(df).mark_bar().encode(
        x=alt.X("cat:N", sort="-y", title=title, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("Agreements:Q", title="Agreements"),
        color=alt.condition(sel, alt.value("#2a6f97"), alt.value("#c9d6df")),
        tooltip=[alt.Tooltip("cat:N", title=title), "Agreements:Q"],
    ).add_params(sel).properties(height=260))
    ev = st.altair_chart(chart, use_container_width=True, on_select="rerun",
                         key=key)
    try:
        return [p["cat"] for p in (ev.selection.get("pts", []) or [])]
    except Exception:
        return []


with tab_portfolio:
    docs = load_documents()
    st.subheader("📊 Portfolio analytics")
    st.caption("Click any chart bar to filter the agreements table below; click "
               "it again (or empty space) to clear.")
    if not docs:
        st.info("No documents loaded.")
    else:
        cats = {"Ratings Downgrade": "downgrade", "NAV Decline": "net asset",
                "Bail-in": "bail-in", "Key Person": "key person",
                "Merger": "merger",
                "Investment Manager Term.": "investment manager"}
        recs = []
        for d in docs.values():
            blob = " ".join(_coerce_list(
                d.get("additional_termination_events"))).lower()
            recs.append({
                "doc_id": d["doc_id"], "counterparty": d["counterparty"],
                "counterparty_type": d["counterparty_type"],
                "governing_law": d["governing_law"],
                "base_currency": d["base_currency"],
                "aet": str(d["automatic_early_termination"]).lower() in
                ("true", "1"),
                "effective_date": d.get("effective_date"),
                "file_name": d.get("file_name"),
                "triggers": [lbl for lbl, kw in cats.items() if kw in blob]})

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Agreements", len(recs))
        m2.metric("AET applies", sum(1 for r in recs if r["aet"]))
        m3.metric("Governing laws", len({r["governing_law"] for r in recs}))
        m4.metric("Base currencies", len({r["base_currency"] for r in recs}))

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Governing law**")
            law_pick = clickable_bar(
                Counter(r["governing_law"] for r in recs), "Governing law",
                "ch_law")
            st.markdown("**Counterparty type**")
            type_pick = clickable_bar(
                Counter(r["counterparty_type"] for r in recs),
                "Counterparty type", "ch_type")
        with cB:
            st.markdown("**Base currency**")
            ccy_pick = clickable_bar(
                Counter(r["base_currency"] for r in recs), "Base currency",
                "ch_ccy")
            st.markdown("**Additional Termination Event triggers**")
            tcnt = Counter()
            for r in recs:
                for t in r["triggers"]:
                    tcnt[t] += 1
            trig_pick = clickable_bar(tcnt, "ATE trigger", "ch_trig")

        filt = recs
        if law_pick:
            filt = [r for r in filt if r["governing_law"] in law_pick]
        if type_pick:
            filt = [r for r in filt if r["counterparty_type"] in type_pick]
        if ccy_pick:
            filt = [r for r in filt if r["base_currency"] in ccy_pick]
        if trig_pick:
            filt = [r for r in filt if any(t in r["triggers"] for t in trig_pick)]

        active = []
        for label, pick in [("Governing law", law_pick),
                            ("Type", type_pick), ("Base ccy", ccy_pick),
                            ("ATE", trig_pick)]:
            if pick:
                active.append("%s ∈ %s" % (label, ", ".join(pick)))

        st.divider()
        if active:
            st.markdown("**ISDA agreements** — %d of %d · filtered by %s"
                        % (len(filt), len(recs), " · ".join(active)))
        else:
            st.markdown("**ISDA agreements** — all %d (click a chart bar to "
                        "filter)" % len(recs))
        table_recs = sorted(filt, key=lambda x: x["doc_id"])
        st.dataframe(
            [{"Doc": r["doc_id"], "Counterparty": r["counterparty"],
              "Type": r["counterparty_type"], "Gov Law": r["governing_law"],
              "AET": "Yes" if r["aet"] else "No",
              "Created Date": r["effective_date"]}
             for r in table_recs],
            use_container_width=True, hide_index=True)
        st.markdown("**Open a document**")
        opts = ["—"] + ["%s — %s" % (r["doc_id"], r["counterparty"])
                        for r in table_recs]
        pick = st.selectbox("Choose an agreement", opts, key="pf_open",
                            label_visibility="collapsed")
        if pick != "—":
            doc_open_controls(table_recs[opts.index(pick) - 1], key_prefix="pf")


with tab_ask:
    st.subheader("💬 Ask the portfolio")
    st.caption("Natural-language questions answered over all 20 agreements — "
               "grounded on the structured clause data + retrieved excerpts, "
               "with citations. Powered by %s." % LLM_MODEL)
    st.markdown("*Try:* “Which counterparties have Automatic Early Termination?” · "
                "“List agreements with an NAV-decline trigger.” · "
                "“Who is governed by English law with a bail-in clause?”")
    aq = st.text_input("Your question", key="ask_q",
                       placeholder="Which counterparties have a NAV-decline "
                                   "Additional Termination Event?")
    if st.button("Ask", type="primary", key="ask_btn") and aq.strip():
        with st.spinner("Analyzing the portfolio…"):
            t0 = time.time()
            try:
                answer, hits = ask_llm(aq.strip())
                lat = (time.time() - t0) * 1000
                st.markdown(answer)
                st.caption("%d ms · grounded on 20 agreements + %d retrieved "
                           "excerpts" % (int(lat), len(hits)))
                try:
                    run_sql("""INSERT INTO {tbl} (audit_id, event_ts, user_email,
                        query, search_mode, filters, num_results, result_doc_ids,
                        top_snippet, latency_ms, app_session)
                        VALUES ('{id}', current_timestamp(), '{u}', '{q}', 'Ask',
                        '{{}}', {n}, array({ids}), '', {lat}, '{sid}')""".format(
                        tbl=AUDIT_TBL, id=str(uuid.uuid4()),
                        u=user_email().replace("'", "''"),
                        q=aq.strip().replace("'", "''"),
                        n=len({h.get("doc_id") for h in hits}),
                        ids=",".join("'%s'" % h.get("doc_id") for h in hits)
                        if hits else "",
                        lat=int(lat),
                        sid=st.session_state.get("sid", "")))
                except Exception:
                    pass
                with st.expander("📎 Sources (retrieved excerpts)"):
                    for h in hits:
                        st.markdown("**[%s p.%s]** %s" % (
                            h.get("doc_id"), h.get("page"),
                            highlight(str(h.get("chunk_text", "")), aq.strip())),
                            unsafe_allow_html=True)
            except Exception as e:
                import traceback
                print("ASK_ERROR:\n" + traceback.format_exc(), flush=True)
                st.error("Ask failed: %s" % str(e)[:200])


with tab_history:
    st.subheader("Search history — who / when / what / result")
    try:
        rows = run_sql("""
            SELECT CAST(event_ts AS STRING) event_ts, user_email, query,
                   search_mode, num_results,
                   concat_ws(', ', result_doc_ids) result_doc_ids, latency_ms
            FROM %s ORDER BY event_ts DESC LIMIT 200""" % AUDIT_TBL)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No searches recorded yet.")
    except Exception as e:
        st.info("Audit table not available yet (%s)." % str(e)[:100])

# --------------------------------------------------------------------------
# Architecture tab: two focused diagrams (build-time + query-time) so each
# stays readable, plus a per-mode methodology table.
# --------------------------------------------------------------------------
ARCH_BUILD_DOT = r"""
digraph Build {
  rankdir=LR;
  graph [fontname="Helvetica", fontsize=13, ranksep=0.8, nodesep=0.5,
         bgcolor="transparent"];
  node  [fontname="Helvetica", fontsize=10.5, shape=box, style="rounded,filled",
         color="#3b3b3b", margin="0.18,0.12"];
  edge  [fontname="Helvetica", fontsize=9.5, color="#5a5a5a"];

  pdf     [label="UC Volume\n20 ISDA PDFs", shape=folder, fillcolor="#eef2f7"];
  parse   [label="1. PARSE\npypdf: text per page", fillcolor="#ffffff"];
  chunk   [label="2. CHUNK\n1 chunk = 1 page\n(20 docs -> 132 chunks)", fillcolor="#fff8e1"];
  tdocs   [label="TABLE documents\n20 rows + full_text", shape=cylinder, fillcolor="#ffffff"];
  tchunks [label="TABLE document_chunks\n132 rows | PK | CDF", shape=cylinder, fillcolor="#e8f5e9"];

  vidx    [label="Vector Search index\ndocument_chunks_index\nembeddings gte-large-en\n(HNSW ANN + BM25 hybrid)", shape=component, fillcolor="#e3f2fd"];
  ftidx   [label="Full-text index (Beta)\ndocument_chunks_fts_index\nBM25, storage-optimized", shape=component, fillcolor="#f2ecfa"];
  extract [label="AI EXTRACT\nai_query(claude-sonnet-4-6)\nfields = FINOS CDM schema", fillcolor="#fff8e1"];
  tex     [label="TABLE clause_extractions\n360 rows (18 clauses x 20)", shape=cylinder, fillcolor="#ffffff"];
  tcoll   [label="TABLE eligible_collateral\n80 structured rules", shape=cylinder, fillcolor="#ffffff"];

  pdf -> parse -> chunk;
  chunk -> tdocs   [label="doc level"];
  chunk -> tchunks [label="page level"];
  tchunks -> vidx  [label="Delta Sync + embed"];
  tchunks -> ftidx [label="Delta Sync (BM25)"];
  tchunks -> extract [label="page-annotated text"];
  extract -> tex;
  extract -> tcoll [label="collateral rules"];
}
"""

ARCH_QUERY_DOT = r"""
digraph Query {
  rankdir=TB;
  graph [fontname="Helvetica", fontsize=13, ranksep=0.7, nodesep=0.55,
         bgcolor="transparent", compound=true];
  node  [fontname="Helvetica", fontsize=11, shape=box, style="rounded,filled",
         color="#3b3b3b", margin="0.18,0.13"];
  edge  [fontname="Helvetica", fontsize=10, color="#5a5a5a"];

  q      [label="Legal Analyst\nkeyword + method + filters\n(SSO -> X-Forwarded-Email)", shape=oval, fillcolor="#eef4ff"];
  router [label="Search — pick Method A (mode) or B", fillcolor="#ffffff"];

  subgraph cluster_A {
    label="Method A  ·  Vector search"; fontsize=13; style="rounded,filled";
    fillcolor="#eef6ee"; color="#7cb37c";

    subgraph cluster_direct {
      label="Direct  -  lexical"; fontsize=11; style="rounded,filled";
      fillcolor="#e8f5e9"; color="#7cb37c";
      e1 [label="SQL ILIKE over document_chunks\nStatement Execution -> SQL Warehouse\nexhaustive, 100% recall", fillcolor="#ffffff"];
    }
    subgraph cluster_sem {
      label="Semantic  -  meaning"; fontsize=11; style="rounded,filled";
      fillcolor="#e3f2fd"; color="#7fb0d8";
      s1 [label="embed query (gte-large-en)\nVector Search query_type=ANN\nHNSW cosine top-k", fillcolor="#ffffff"];
    }
    subgraph cluster_hyb {
      label="Hybrid (default)  -  both"; fontsize=11; style="rounded,filled";
      fillcolor="#f2ecfa"; color="#b892d0";
      h1 [label="Direct SQL lane (100% floor)\n  UNION\nVector Search query_type=HYBRID\n(vector + BM25, rank-fused)", fillcolor="#ffffff"];
    }
  }

  subgraph cluster_B {
    label="Method B  ·  Full-text index (BM25, Beta)"; fontsize=13;
    style="rounded,filled"; fillcolor="#f5eefb"; color="#b892d0";
    b1 [label="Vector Search query_type=FULL_TEXT\nstorage-optimized endpoint\nBM25 relevance ranking", fillcolor="#ffffff"];
  }

  merge   [label="MERGE + de-dupe by document\nhighlight keyword + attach page ref", fillcolor="#ffffff"];
  results [label="Results\ndocuments + highlighted snippets\n+ page refs + Open/Download PDF", shape=note, fillcolor="#eef4ff"];
  audit   [label="INSERT search_audit\nwho / when / what / result / latency", shape=cylinder, fillcolor="#fff8e1"];

  q -> router;
  router -> e1 [label="A · Direct"];
  router -> s1 [label="A · Semantic"];
  router -> h1 [label="A · Hybrid"];
  router -> b1 [label="B · BM25"];
  e1 -> merge;  s1 -> merge;  h1 -> merge;  b1 -> merge;
  merge -> results;
  router -> audit [label="every search", style=dashed];
}
"""


# AI features (extraction -> CDM digitization, and grounded Q&A).
ARCH_AI_DOT = r"""
digraph AI {
  rankdir=LR;
  graph [fontname="Helvetica", fontsize=13, ranksep=0.7, nodesep=0.5,
         bgcolor="transparent"];
  node  [fontname="Helvetica", fontsize=10.5, shape=box, style="rounded,filled",
         color="#3b3b3b", margin="0.18,0.12"];
  edge  [fontname="Helvetica", fontsize=9.5, color="#5a5a5a"];
  llm   [label="Model Serving\ndatabricks-claude-sonnet-4-6\n(ai_query)", fillcolor="#fff8e1"];

  subgraph cluster_ex {
    label="Extract  ->  Digitize (Extract tab)"; fontsize=12; style="rounded,filled";
    fillcolor="#eef6ee"; color="#9fca9f";
    x0 [label="document_chunks\n(page-annotated text)", shape=cylinder, fillcolor="#ffffff"];
    x1 [label="clause_extractions\nvalue+page+snippet+confidence", shape=cylinder, fillcolor="#ffffff"];
    x2 [label="build_cdm() + validate_cdm()\nCDM LegalAgreement JSON\n(jsonschema-validated)", fillcolor="#e3f2fd"];
    x0 -> x1 [label="ai_query\n(fields from CDM schema)"];
    x1 -> x2 [label="map + validate"];
  }

  subgraph cluster_ask {
    label="Ask  ·  grounded Q&A (Ask tab)"; fontsize=12; style="rounded,filled";
    fillcolor="#eef4ff"; color="#9dbcf0";
    a0 [label="question", shape=oval, fillcolor="#ffffff"];
    a1 [label="context =\nstructured summary of 20 docs\n+ hybrid-retrieved excerpts", fillcolor="#ffffff"];
    a2 [label="grounded answer\n+ [doc_id] citations", shape=note, fillcolor="#ffffff"];
    a0 -> a1 [label="retrieve"];
    a1 -> a2 [label="ai_query"];
  }

  x0 -> llm [style=dashed, dir=both, label="extract"];
  a1 -> llm [style=dashed, dir=both, label="answer"];
}
"""

ARCH_TECH_DOT = r"""
digraph Tech {
  rankdir=TB;
  graph [fontname="Helvetica", fontsize=13, ranksep=0.75, nodesep=0.55,
         bgcolor="transparent", compound=true];
  node  [fontname="Helvetica", fontsize=10.5, shape=box, style="rounded,filled",
         color="#3b3b3b", margin="0.18,0.13"];
  edge  [fontname="Helvetica", fontsize=9.5, color="#5a5a5a"];

  subgraph cluster_client {
    label="Client"; fontsize=12; style="rounded,filled"; fillcolor="#eef4ff"; color="#9dbcf0";
    browser [label="Legal Analyst\nweb browser", shape=oval, fillcolor="#ffffff"];
  }

  subgraph cluster_app {
    label="Application tier  -  Databricks App (managed compute)"; fontsize=12;
    style="rounded,filled"; fillcolor="#f3f9f3"; color="#9fca9f";
    streamlit [label="Streamlit app  (app.py)\nserved on :8000", fillcolor="#ffffff"];
    sp        [label="App Service Principal\n(app service principal)\n(WorkspaceClient OAuth)", shape=component, fillcolor="#fff8e1"];
    streamlit -> sp [label="authenticates as", style=dashed];
  }

  subgraph cluster_api {
    label="API tier  -  Databricks REST (control plane)"; fontsize=12;
    style="rounded,filled"; fillcolor="#faf3fb"; color="#c9a3d0";
    stmt   [label="SQL Statement Execution API\n/api/2.0/sql/statements", fillcolor="#ffffff"];
    vsrest [label="Vector Search REST API\nsimilarity_search", fillcolor="#ffffff"];
    files  [label="Files API\n/api/2.0/fs/files  (volume I/O)", fillcolor="#ffffff"];
  }

  subgraph cluster_compute {
    label="Compute tier"; fontsize=12; style="rounded,filled"; fillcolor="#fff4ec"; color="#e0b58a";
    wh     [label="Serverless SQL Warehouse\nyour-sql-warehouse-id\n(SQL + ai_query + audit)", shape=cylinder, fillcolor="#ffffff"];
    vsep   [label="Vector Search Endpoint\nisda-search-endpoint (STANDARD)\n(Method A semantic / hybrid)", fillcolor="#ffffff"];
    embed  [label="Model Serving\ndatabricks-gte-large-en\n(embeddings)", fillcolor="#ffffff"];
    llm    [label="Model Serving\ndatabricks-claude-sonnet-4-6\n(Extract + Ask via ai_query)", fillcolor="#fff8e1"];
    vsepft [label="Vector Search Endpoint\nisda-fts-endpoint (STORAGE-OPTIMIZED)\n(Method B BM25, Beta)", fillcolor="#f2ecfa"];
  }

  subgraph cluster_uc {
    label="Data & governance tier  -  Unity Catalog: your-catalog.isda_search"; fontsize=12;
    style="rounded,filled"; fillcolor="#eef2f7"; color="#a9b6c8";
    vol     [label="Volume: contracts\n20 PDFs (+ staging)", shape=folder, fillcolor="#ffffff"];
    tdocs   [label="TABLE documents", shape=cylinder, fillcolor="#ffffff"];
    tchunks [label="TABLE document_chunks\nPK + CDF", shape=cylinder, fillcolor="#e8f5e9"];
    tex     [label="TABLE clause_extractions", shape=cylinder, fillcolor="#ffffff"];
    tcoll   [label="TABLE eligible_collateral", shape=cylinder, fillcolor="#ffffff"];
    taudit  [label="TABLE search_audit", shape=cylinder, fillcolor="#fff8e1"];
    vsidx   [label="Vector Search Index\ndocument_chunks_index\n(Delta Sync, embeddings)", shape=component, fillcolor="#e3f2fd"];
    ftsidx  [label="Full-text Index\ndocument_chunks_fts_index\n(BM25, no embeddings, Beta)", shape=component, fillcolor="#f2ecfa"];
  }

  browser -> streamlit [label="HTTPS + workspace SSO/OAuth\n(X-Forwarded-Email)"];

  sp -> stmt   [label="as app SP"];
  sp -> vsrest [label="as app SP"];
  files -> vol [label="upload (build time)", style=dotted];

  stmt   -> wh   [label="run SQL  (CAN_USE)"];
  vsrest -> vsep [label="query  (endpoint CAN_USE)"];

  wh -> tdocs   [label="SELECT"];
  wh -> tchunks [label="SELECT (ILIKE)"];
  wh -> taudit  [label="SELECT + INSERT"];
  wh -> tex     [label="ai_query -> SELECT/INSERT", style=dashed];
  wh -> tcoll   [label="SELECT", style=dotted];
  wh -> llm     [label="ai_query (Extract + Ask)", style=dashed];

  vsep  -> vsidx  [label="ANN + keyword"];
  vsep  -> embed  [label="embed query", style=dashed];
  vsidx -> tchunks [label="Delta Sync (CDF)", style=dotted, dir=back];

  vsrest  -> vsepft [label="Method B (Beta)\nquery_type=FULL_TEXT", style=dashed, color="#9161b8", fontcolor="#9161b8"];
  vsepft  -> ftsidx [label="BM25", color="#9161b8"];
  ftsidx  -> tchunks [label="Delta Sync", style=dotted, dir=back];
}
"""

with tab_arch:
    st.subheader("Solution architecture")
    st.caption("Four views: how documents are indexed & extracted (build time), "
               "how a search runs (Method A / B), the AI features "
               "(extraction → CDM, and Ask), and the technical components.")
    st.markdown("**Tabs:** 📊 Portfolio (analytics + click-to-filter) · 📚 Documents "
                "· 🧬 Extract (AI clause register + CDM) · 🔎 Search (Method A/B) · "
                "💬 Ask (grounded Q&A) · 🕑 History (audit) · 🏗️ Architecture.")

    st.markdown("### A. Build time — parse → chunk → index → extract")
    st.graphviz_chart(ARCH_BUILD_DOT, use_container_width=True)
    st.markdown("""
- **Parse** — `02_ingest.py` reads each PDF with **pypdf**, one text string per
  page. *(For scanned PDFs the production path is `ai_parse_document`.)*
- **Chunk** — **page-level**: one chunk per page (`chunk_id=<doc>_p<n>`), 20 docs
  → **132 chunks**, giving a precise page reference and a coherent retrieval unit.
- **Store** — Delta tables via `read_files()` CTAS: **`documents`** (+ `full_text`)
  and **`document_chunks`** (**PK + Change Data Feed**, required by the indexes).
- **Two indexes** off `document_chunks` (both Delta-Sync): the **Vector Search
  index** (`document_chunks_index`, managed **`gte-large-en`** embeddings + HNSW,
  hybrid-capable) and the **full-text BM25 index** (`document_chunks_fts_index`,
  storage-optimized, Beta).
- **AI extract** — `07/08` run **`ai_query(claude-sonnet-4-6)`** over the page
  text (fields defined by the **FINOS CDM** schema) → **`clause_extractions`**
  (18 clauses × 20) and structured **`eligible_collateral`** rules.
""")

    st.markdown("### B. Search — Method A (Direct / Semantic / Hybrid) vs Method B (BM25)")
    st.graphviz_chart(ARCH_QUERY_DOT, use_container_width=True)
    st.markdown("**Method A · Vector search** — three modes:")
    st.markdown("""
| | **Direct** | **Semantic** | **Hybrid** *(default)* |
|---|---|---|---|
| **Technique** | Case-insensitive substring (SQL `ILIKE`) + metadata filters | Vector nearest-neighbour on the query embedding | Direct lane **∪** Vector Search `HYBRID` (vector **+** BM25, rank-fused) |
| **Engine / API** | SQL Warehouse via **Statement Execution API** | **Vector Search REST**, `query_type="ANN"` (embed `gte-large-en`) | **SQL Warehouse** *and* **Vector Search REST** `query_type="HYBRID"` |
| **Matches on** | Literal characters / phrase | Meaning & paraphrase | Literal **and** meaning |
| **Recall** | **100%** — exhaustive, no top-k cutoff | top-k (approximate) | **≥ Direct** — the union can only add documents |
| **Best for** | party names, LEIs, amounts, clause labels | concepts, synonyms | everyday legal search — the safe default |
""")
    st.markdown("**Method A vs Method B:**")
    st.markdown("""
| | **Method A — Vector search** | **Method B — Full-text index (BM25)** *(Beta)* |
|---|---|---|
| **Engines** | SQL Warehouse **+** Vector Search (STANDARD, embeddings) | Vector Search **storage-optimized** endpoint |
| **API** | Statement Execution + Vector Search REST (`ANN`/`HYBRID`) | Vector Search REST, `query_type="FULL_TEXT"` |
| **Embeddings** | yes (`gte-large-en`, 1024-dim) | none — pure keyword |
| **Ranking** | Direct-first, then similarity / fused score | BM25 relevance score |
| **Scales to** | good; Direct lane scans the table | **billions** of rows, 10–20× faster indexing |
""")
    st.info("**Trade-off:** Method A (default) gives the best overall answer — "
            "guaranteed exact recall (Direct) plus semantic matches — while "
            "maintaining embeddings. Method B is a pure, managed, horizontally-"
            "scalable keyword index — the right tool for huge corpora or keyword-"
            "only ranking. Complementary, not exclusive.")

    st.markdown("### C. AI features — Extraction → CDM, and Ask")
    st.graphviz_chart(ARCH_AI_DOT, use_container_width=True)
    st.markdown("""
- **Extract → Digitize** (🧬 Extract) — `ai_query(claude-sonnet-4-6)` reads each
  agreement into the clause register (value + page + snippet + confidence), then
  `build_cdm()` maps it to a **FINOS CDM `LegalAgreement`** and `validate_cdm()`
  checks it against a CDM-aligned JSON Schema. The extraction field list is
  **derived from the CDM schema** (one source of truth).
- **Ask** (💬 Ask) — grounded Q&A: a compact structured summary of all 20 docs
  **+** hybrid-retrieved excerpts are fed to `ai_query`, which answers with
  **`[doc_id]` citations**. Logged to `search_audit` as mode `Ask`.
""")

    st.markdown("### D. Technical architecture — components & connections")
    st.graphviz_chart(ARCH_TECH_DOT, use_container_width=True)
    st.markdown("""
The runtime is fully **Databricks-native, serverless, and governed by Unity
Catalog** — no external services:

- **Client** → the **Databricks App** over HTTPS behind workspace **SSO**; the
  analyst's identity arrives as the `X-Forwarded-Email` header.
- **Application tier** — a **Streamlit** process on Databricks App managed compute.
  All backend calls go out as the **app Service Principal** via `WorkspaceClient`
  OAuth (no user tokens in the app).
- **API tier** — three Databricks REST APIs: **SQL Statement Execution** (both
  search SQL and the audit `INSERT`), **Vector Search REST** (semantic/hybrid
  retrieval), and the **Files API** (volume upload, used at build time).
- **API tier** also carries the **Files API** (volume I/O + in-app PDF page
  images) at build/serve time.
- **Compute tier** — the **Serverless SQL Warehouse** runs SQL *and* `ai_query`;
  the **Vector Search endpoints** (STANDARD for Method A, storage-optimized for
  Method B) serve the indexes; **`gte-large-en`** embeds queries; and
  **`claude-sonnet-4-6`** powers Extract + Ask via `ai_query`.
- **Data & governance tier** — the **UC Volume** holds the PDFs; **`documents`**,
  **`document_chunks`** (PK + CDF), **`clause_extractions`**, **`eligible_collateral`**
  and **`search_audit`** are Delta tables; both indexes Delta-Sync from
  `document_chunks`.
""")

    st.markdown("### Access control — app service principal grants")
    st.dataframe([
        {"Object": "Catalog / Schema (isda_search)", "Grant": "USE CATALOG, USE SCHEMA"},
        {"Object": "TABLE documents", "Grant": "SELECT"},
        {"Object": "TABLE document_chunks", "Grant": "SELECT"},
        {"Object": "TABLE search_audit", "Grant": "SELECT, MODIFY"},
        {"Object": "TABLE clause_extractions", "Grant": "SELECT, MODIFY"},
        {"Object": "TABLE eligible_collateral", "Grant": "SELECT"},
        {"Object": "VOLUME contracts", "Grant": "READ VOLUME"},
        {"Object": "Vector Search index (document_chunks_index)", "Grant": "SELECT"},
        {"Object": "SQL Warehouse (your-sql-warehouse-id)", "Grant": "CAN_USE"},
        {"Object": "Vector Search endpoint (isda-search-endpoint)", "Grant": "CAN_USE"},
        {"Object": "Full-text index (document_chunks_fts_index) — Method B",
         "Grant": "SELECT"},
        {"Object": "Vector Search endpoint (isda-fts-endpoint) — Method B",
         "Grant": "CAN_USE"},
        {"Object": "Model Serving (claude-sonnet-4-6, gte-large-en)",
         "Grant": "system endpoints — open (no grant)"},
    ], use_container_width=True, hide_index=True)

    st.markdown("### Live coordinates")
    st.dataframe([
        {"Component": "Catalog.schema", "Value": "%s.%s" % (config.get("catalog"),
                                                            config.get("schema"))},
        {"Component": "Volume", "Value": "contracts (20 PDFs)"},
        {"Component": "Table — documents", "Value": DOCS_TBL},
        {"Component": "Table — document_chunks (PK + CDF)", "Value": CHUNKS_TBL},
        {"Component": "Table — clause_extractions", "Value": EXTRACTIONS_TBL or "-"},
        {"Component": "Table — eligible_collateral", "Value": COLLATERAL_TBL or "-"},
        {"Component": "Table — search_audit", "Value": AUDIT_TBL},
        {"Component": "Vector Search endpoint (Method A)", "Value": VS_ENDPOINT},
        {"Component": "Vector Search index (Method A)", "Value": VS_INDEX},
        {"Component": "Embedding model", "Value": "databricks-gte-large-en (1024-dim)"},
        {"Component": "LLM (Extract + Ask)", "Value": LLM_MODEL or "-"},
        {"Component": "Full-text endpoint (Method B, Beta)",
         "Value": "%s (STORAGE_OPTIMIZED)" % (FTS_ENDPOINT or "-")},
        {"Component": "Full-text index (Method B, Beta)", "Value": FTS_INDEX or "-"},
        {"Component": "SQL Warehouse", "Value": WAREHOUSE},
        {"Component": "APIs used", "Value": "Statement Execution · Vector Search "
         "REST · Files API"},
    ], use_container_width=True, hide_index=True)
