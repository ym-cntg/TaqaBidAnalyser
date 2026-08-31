"""Shared Databricks Model Serving config -- used by every AI feature in
this app (backend/api/negotiation_narrative.py, backend/api/beta_pricing.py)
so there's exactly one place that knows the env var name and the
not-configured error message.

Auth reuses WorkspaceClient()'s auto-detected credentials (same as
backend/db.py's Config()-based SQL connection) -- no new secret to manage,
and no external LLM API involved. See databricks/FINDINGS.md for the full
guardrails writeup behind this choice.
"""

import os

from fastapi import HTTPException


def get_llm_endpoint_name() -> str:
    endpoint = os.environ.get("DATABRICKS_LLM_ENDPOINT")
    if not endpoint:
        raise HTTPException(
            status_code=503,
            detail=(
                "not_configured: DATABRICKS_LLM_ENDPOINT is not set. Find (or create) a "
                "Model Serving endpoint name under the workspace's Serving UI and set it "
                "as this env var -- the app's service principal also needs 'Can Query' "
                "permission granted on that endpoint."
            ),
        )
    return endpoint
