"""Cliente GCS compartilhado: credenciais existentes ou acesso publico explicito."""
from __future__ import annotations

import base64
import json
import os


def auth_mode():
    mode = os.getenv("GCS_AUTH_MODE", "auto").strip().lower()
    if mode not in {"auto", "public", "authenticated"}:
        raise ValueError("GCS_AUTH_MODE deve ser auto, public ou authenticated.")
    return mode


def credential_pair(settings=None, *, tcm=False):
    from google.auth.credentials import AnonymousCredentials

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "maestro-rreo"
    if auth_mode() == "public":
        return AnonymousCredentials(), project

    def configured(attrs, names):
        for attr in attrs:
            value = getattr(settings, attr, "") if settings is not None else ""
            if value and str(value).strip():
                return str(value).strip()
        for name in names:
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    raw_keys = ["GOOGLE_SERVICE_ACCOUNT_JSON", "GCP_SERVICE_ACCOUNT_JSON"]
    b64_keys = ["GOOGLE_SERVICE_ACCOUNT_JSON_B64", "GCP_SERVICE_ACCOUNT_JSON_B64"]
    if tcm:
        raw_keys = ["TCM_GOOGLE_SERVICE_ACCOUNT_JSON", "TCM_GCP_SERVICE_ACCOUNT_JSON"] + raw_keys
        b64_keys = ["TCM_GOOGLE_SERVICE_ACCOUNT_JSON_B64", "TCM_GCP_SERVICE_ACCOUNT_JSON_B64"] + b64_keys
    raw = configured(("service_account_json", "gcp_service_account_json"), raw_keys)
    encoded = configured(("service_account_json_b64", "gcp_service_account_json_b64"), b64_keys)
    if encoded and not raw:
        raw = base64.b64decode(encoded, validate=True).decode("utf-8")
    if raw:
        from google.oauth2 import service_account
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info), info.get("project_id") or project

    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    try:
        credentials, adc_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return credentials, adc_project or project
    except DefaultCredentialsError:
        if auth_mode() == "authenticated" or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            raise
        # Ausencia de credenciais nao impede acesso a um bucket publico.
        return AnonymousCredentials(), project


def storage_client(settings=None, *, tcm=False):
    from google.cloud import storage
    credentials, project = credential_pair(settings, tcm=tcm)
    return storage.Client(project=project, credentials=credentials)

