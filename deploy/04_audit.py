"""Step 4: Create the search audit table (who / when / what / result)."""
import dbx


def main():
    w = dbx.client()
    r = dbx.load_resolved()
    dbx.run_sql(w, """
    CREATE TABLE IF NOT EXISTS {tbl} (
        audit_id      STRING,
        event_ts      TIMESTAMP,
        user_email    STRING,
        query         STRING,
        search_mode   STRING,
        filters       STRING,
        num_results   INT,
        result_doc_ids ARRAY<STRING>,
        top_snippet   STRING,
        latency_ms    INT,
        app_session   STRING
    ) TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """.format(tbl=r["audit_table"]))
    print("audit table ready:", r["audit_table"])


if __name__ == "__main__":
    main()
