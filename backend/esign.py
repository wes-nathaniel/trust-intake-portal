"""Dropbox Sign integration helpers.

Graceful no-op behaviour when DROPBOX_SIGN_API_KEY is blank.
All SDK calls are wrapped to raise clean HTTPException so server.py stays clean.
"""
import os
import tempfile
from typing import Optional
from dropbox_sign import ApiClient, Configuration, apis, models

DROPBOX_SIGN_API_KEY = os.environ.get("DROPBOX_SIGN_API_KEY", "").strip()
TEST_MODE = os.environ.get("DROPBOX_SIGN_TEST_MODE", "true").lower() != "false"


def is_enabled() -> bool:
    return bool(DROPBOX_SIGN_API_KEY)


def _client() -> ApiClient:
    cfg = Configuration(username=DROPBOX_SIGN_API_KEY)
    return ApiClient(configuration=cfg)


def send_signature_request(pdf_bytes: bytes, filename: str, signer_email: str,
                           signer_name: str, title: str, subject: str,
                           message: str) -> dict:
    """Email-based signature request. Returns {signature_request_id, status, details_url}."""
    if not is_enabled():
        raise RuntimeError("Dropbox Sign is not configured")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        tmp.write(pdf_bytes)
        tmp.flush(); tmp.close()
        with _client() as api_client:
            api = apis.SignatureRequestApi(api_client)
            signer = models.SubSignatureRequestSigner(
                email_address=signer_email, name=signer_name, order=0
            )
            req = models.SignatureRequestSendRequest(
                title=title,
                subject=subject,
                message=message,
                signers=[signer],
                files=[open(tmp.name, "rb")],
                test_mode=TEST_MODE,
            )
            resp = api.signature_request_send(req).to_dict()["signature_request"]
            return {
                "signature_request_id": resp["signature_request_id"],
                "is_complete": resp.get("is_complete", False),
                "details_url": resp.get("details_url"),
                "signatures": resp.get("signatures", []),
            }
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass


def get_status(signature_request_id: str) -> dict:
    if not is_enabled():
        raise RuntimeError("Dropbox Sign is not configured")
    with _client() as api_client:
        api = apis.SignatureRequestApi(api_client)
        resp = api.signature_request_get(signature_request_id=signature_request_id).to_dict()["signature_request"]
        return {
            "signature_request_id": signature_request_id,
            "is_complete": resp.get("is_complete", False),
            "signatures": resp.get("signatures", []),
            "details_url": resp.get("details_url"),
        }


def download_signed_pdf(signature_request_id: str) -> bytes:
    if not is_enabled():
        raise RuntimeError("Dropbox Sign is not configured")
    with _client() as api_client:
        api = apis.SignatureRequestApi(api_client)
        # Returns a local temp file path per SDK convention
        resp = api.signature_request_files(signature_request_id=signature_request_id, file_type="pdf")
        # resp is a file-like returned by urllib3; check both attrs
        path = getattr(resp, "name", None) or getattr(resp, "path", None)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        # Some SDK versions return the raw bytes directly
        if isinstance(resp, (bytes, bytearray)):
            return bytes(resp)
        raise RuntimeError("Unable to read signed PDF from SDK response")


def cancel(signature_request_id: str) -> None:
    if not is_enabled():
        return
    with _client() as api_client:
        api = apis.SignatureRequestApi(api_client)
        api.signature_request_cancel(signature_request_id=signature_request_id)
