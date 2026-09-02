"""Parse authenticated user identity forwarded by Azure Container Apps Easy Auth."""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CLIENT_PRINCIPAL_HEADER = "x-ms-client-principal"

_OBJECT_ID_CLAIM = "http://schemas.microsoft.com/identity/claims/objectidentifier"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    display_name: str


def _dev_mode_enabled() -> bool:
    return os.getenv("QUOTA_DEV_MODE", "").strip() == "1"


def _claim_value(claims: list[dict[str, str]], *types: str) -> str | None:
    wanted = set(types)
    for claim in claims:
        claim_type = claim.get("typ")
        if claim_type in wanted:
            value = claim.get("val")
            if value:
                return value
    return None


def parse_client_principal(header_value: str | None) -> AuthenticatedUser | None:
    if not header_value:
        return None

    try:
        decoded = base64.b64decode(header_value).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        logger.warning("Invalid X-MS-CLIENT-PRINCIPAL header")
        return None

    claims = payload.get("claims")
    if not isinstance(claims, list):
        return None

    typed_claims = [claim for claim in claims if isinstance(claim, dict)]

    user_id = _claim_value(typed_claims, "oid", _OBJECT_ID_CLAIM, "sub")
    if not user_id:
        return None

    display_name = _claim_value(
        typed_claims,
        "name",
        "preferred_username",
        "email",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    )
    if not display_name:
        display_name = user_id

    return AuthenticatedUser(user_id=user_id, display_name=display_name)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def get_authenticated_user(headers: Mapping[str, str] | None = None) -> AuthenticatedUser | None:
    dev_user = os.getenv("QUOTA_DEV_USER", "").strip()
    if _dev_mode_enabled() and dev_user:
        return AuthenticatedUser(user_id=dev_user, display_name=dev_user)

    if headers is None:
        try:
            import streamlit as st

            headers = st.context.headers
        except Exception:
            headers = {}

    principal = parse_client_principal(_header_value(headers, CLIENT_PRINCIPAL_HEADER))
    if principal is not None:
        return principal

    return None


def identity_required() -> bool:
    if _dev_mode_enabled():
        return False
    return bool(os.getenv("AZURE_STORAGE_ACCOUNT", "").strip())
