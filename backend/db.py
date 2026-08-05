"""Databricks SQL warehouse connection helper, shared by every backend module
that needs to query Unity Catalog."""

import os

from databricks import sql
from databricks.sdk.core import Config

CATALOG = "ingestion_framework_test"
SCHEMA = "bid_data_exploration"


def get_connection():
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if not http_path:
        raise RuntimeError(
            "DATABRICKS_HTTP_PATH is not set. Find it under the target SQL "
            "warehouse's 'Connection details' tab in the Databricks UI."
        )

    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        # Explicit personal access token -- simplest path for local dev.
        server_hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
        return sql.connect(
            server_hostname=server_hostname,
            http_path=http_path,
            access_token=token,
        )

    # No token set -- fall back to the Databricks SDK's default credential
    # chain (a configured CLI profile locally, or auto-injected credentials
    # when running as a Databricks App). This is the path a real deployment
    # is expected to use.
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
    )
