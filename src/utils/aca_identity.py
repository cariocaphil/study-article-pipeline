"""Parse authenticated user identity forwarded by Azure Container Apps Easy Auth."""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

logger = logging.getLogger(__name__)

CLIENT_PRINCIPAL_HEADER = "x-ms-client-principal"
CLIENT_PRINCIPAL_ID_HEADER = "x-ms-client-principal-id"
CLIENT_PRINCIPAL_NAME_HEADER = "x-ms-client-principal-name"
CLIENT_PRINCIPAL_IDP_HEADER = "x-ms-client-principal-idp"

_OBJECT_ID_CLAIM = "http://schemas.microsoft.com/identity/claims/objectidentifier"
_NAME_IDENTIFIER_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    display_name: str
    identity_provider: str | None = None


def _dev_mode_enabled() -> bool:
    return os.getenv("QUOTA_DEV_MODE", "").strip() == "1"


def identity_provider_label(identity_provider: str | None) -> str | None:
    if identity_provider == "aad":
        return "Microsoft"
    if identity_provider == "google":
        return "Google"
    return identity_provider


def login_url(provider: str, *, redirect_path: str = "/") -> str:
    encoded_redirect = quote(redirect_path, safe="/")
    return f"/.auth/login/{provider}?post_login_redirect_uri={encoded_redirect}"


def logout_url(*, redirect_path: str = "/") -> str:
    encoded_redirect = quote(redirect_path, safe="/")
    return f"/.auth/logout?post_logout_redirect_uri={encoded_redirect}"


def _claim_value(claims: list[dict[str, str]], *types: str) -> str | None:
    wanted = set(types)
    for claim in claims:
        claim_type = claim.get("typ")
        if claim_type in wanted:
            value = claim.get("val")
            if value:
                return value
    return None


def _canonical_user_id(*, identity_provider: str | None, raw_id: str) -> str:
    """Keep Microsoft object IDs unchanged; namespace other providers."""
    if identity_provider == "aad":
        return raw_id
    if identity_provider:
        return f"{identity_provider}:{raw_id}"
    return raw_id


def _resolve_user_id_from_claims(
    typed_claims: list[dict[str, str]],
    identity_provider: str | None,
) -> str | None:
    if identity_provider == "aad":
        raw_id = _claim_value(typed_claims, "oid", _OBJECT_ID_CLAIM)
    else:
        raw_id = _claim_value(typed_claims, "sub", _NAME_IDENTIFIER_CLAIM)

    if not raw_id:
        return None

    return _canonical_user_id(identity_provider=identity_provider, raw_id=raw_id)


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

    typed_claims: list[dict[str, str]] = []
    for claim in cast(list[object], claims):
        if not isinstance(claim, dict):
            continue
        typed_claim: dict[str, str] = {}
        for key, value in cast(dict[object, object], claim).items():
            if isinstance(key, str) and isinstance(value, str):
                typed_claim[key] = value
        typed_claims.append(typed_claim)

    identity_provider = payload.get("auth_typ")
    if not isinstance(identity_provider, str) or not identity_provider:
        identity_provider = None

    user_id = _resolve_user_id_from_claims(typed_claims, identity_provider)
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

    return AuthenticatedUser(
        user_id=user_id,
        display_name=display_name,
        identity_provider=identity_provider,
    )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _user_from_aca_headers(headers: Mapping[str, str]) -> AuthenticatedUser | None:
    identity_provider = _header_value(headers, CLIENT_PRINCIPAL_IDP_HEADER)
    raw_id = _header_value(headers, CLIENT_PRINCIPAL_ID_HEADER)
    if not raw_id or not identity_provider:
        return None

    display_name = _header_value(headers, CLIENT_PRINCIPAL_NAME_HEADER) or raw_id
    return AuthenticatedUser(
        user_id=_canonical_user_id(identity_provider=identity_provider, raw_id=raw_id),
        display_name=display_name,
        identity_provider=identity_provider,
    )


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

    return _user_from_aca_headers(headers)


def identity_required() -> bool:
    if _dev_mode_enabled():
        return False
    return bool(os.getenv("AZURE_STORAGE_ACCOUNT", "").strip())
