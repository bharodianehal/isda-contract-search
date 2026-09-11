"""Run the full deployment pipeline in order.
Usage:  ../.venv/bin/python run_all.py
Prereqs: edit ../config.env, generate contracts (generator/generate_contracts.py),
and `databricks auth login --host <DBX_HOST> --profile <DBX_PROFILE>`.

00 creates the app first so its service principal exists; 05 runs LAST to grant
that SP on every object and deploy the app code.
"""
import runpy
import sys

STEPS = ["00_create_app.py",        # create app -> write APP_SP to config.env
         "01_setup_uc.py",          # catalog/schema/volume + upload PDFs
         "02_ingest.py",            # parse -> documents + document_chunks
         "03_vector_search.py",     # Method A vector index
         "04_audit.py",             # search_audit table
         "validate_search.py",      # golden-keyword recall test
         "06_fulltext_index.py",    # Method B (needs Full Text preview enabled)
         "07_extract_clauses.py",   # AI clause extraction (CDM-driven schema)
         "08_eligible_collateral.py",  # structured eligible-collateral rules
         "05_deploy_app.py"]        # grant app SP on ALL objects + deploy


def main():
    only = sys.argv[1:] or STEPS
    for s in STEPS:
        if s not in only and only != STEPS:
            continue
        print("\n" + "=" * 70 + "\n>>> " + s + "\n" + "=" * 70)
        runpy.run_path(s, run_name="__main__")


if __name__ == "__main__":
    main()
