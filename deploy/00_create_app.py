"""Step 0: Create the Databricks App and capture its service-principal id.

Run FIRST in a fresh environment: the app's service principal must exist before
later steps can grant it access. Writes APP_SP back into config.env so every
subsequent script (and the grants in 05) picks it up automatically.
"""
from databricks.sdk.service.apps import App

import dbx


def main():
    w = dbx.client()
    try:
        app = w.apps.get(name=dbx.APP_NAME)
        print("app already exists:", dbx.APP_NAME)
    except Exception:
        print("creating app:", dbx.APP_NAME)
        app = w.apps.create(app=App(
            name=dbx.APP_NAME,
            description="ISDA contract keyword search for legal analysts")).result()
    sp = app.service_principal_client_id
    print("app service principal client_id:", sp)
    dbx.set_config("APP_SP", sp)
    print("wrote APP_SP to config.env")


if __name__ == "__main__":
    main()
