"""Tests for src/utils/aca_identity.py."""

import base64
import json
from typing import Any

import pytest

from src.utils.aca_identity import (
    AuthenticatedUser,
    get_authenticated_user,
    identity_provider_label,
    identity_required,
    login_url,
    logout_url,
    parse_client_principal,
)

_NAME_IDENTIFIER_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"


def _encode_principal(*claims: tuple[str, str], auth_typ: str = "aad") -> str:
    payload: dict[str, Any] = {
        "auth_typ": auth_typ,
        "claims": [{"typ": typ, "val": val} for typ, val in claims],
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def test_parse_client_principal_reads_oid_and_name_for_microsoft():
    header = _encode_principal(
        ("oid", "user-123"),
        ("name", "Ada Lovelace"),
    )

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(
        user_id="user-123",
        display_name="Ada Lovelace",
        identity_provider="aad",
    )


def test_parse_client_principal_reads_google_nameidentifier_claim():
    header = _encode_principal(
        (_NAME_IDENTIFIER_CLAIM, "google-sub-456"),
        ("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", "ada@example.com"),
        auth_typ="google",
    )

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(
        user_id="google:google-sub-456",
        display_name="ada@example.com",
        identity_provider="google",
    )


def test_parse_client_principal_falls_back_to_sub_for_google():
    header = _encode_principal(
        ("sub", "google-sub-789"),
        ("email", "ada@example.com"),
        auth_typ="google",
    )

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(
        user_id="google:google-sub-789",
        display_name="ada@example.com",
        identity_provider="google",
    )


def test_parse_client_principal_returns_none_for_invalid_header():
    assert parse_client_principal(None) is None
    assert parse_client_principal("not-base64") is None


def test_parse_client_principal_skips_non_string_claim_entries() -> None:
    payload: dict[str, Any] = {
        "auth_typ": "aad",
        "claims": [
            "not-a-dict",
            {"typ": "oid", "val": 123},
            {"typ": "oid", "val": "user-999"},
            {"typ": "name", "val": "Ada"},
        ],
    }
    header = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(
        user_id="user-999",
        display_name="Ada",
        identity_provider="aad",
    )


def test_get_authenticated_user_uses_dev_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUOTA_DEV_MODE", "1")
    monkeypatch.setenv("QUOTA_DEV_USER", "local-dev")

    user = get_authenticated_user(headers={})

    assert user == AuthenticatedUser(user_id="local-dev", display_name="local-dev")


def test_get_authenticated_user_reads_aca_principal_header_for_microsoft():
    header = _encode_principal(("oid", "aca-user"), ("name", "Reviewer"))
    user = get_authenticated_user(headers={"X-MS-CLIENT-PRINCIPAL": header})

    assert user == AuthenticatedUser(
        user_id="aca-user",
        display_name="Reviewer",
        identity_provider="aad",
    )


def test_get_authenticated_user_falls_back_to_aca_shorthand_headers_for_google():
    user = get_authenticated_user(
        headers={
            "X-MS-CLIENT-PRINCIPAL-IDP": "google",
            "X-MS-CLIENT-PRINCIPAL-ID": "google-sub-999",
            "X-MS-CLIENT-PRINCIPAL-NAME": "ada@example.com",
        }
    )

    assert user == AuthenticatedUser(
        user_id="google:google-sub-999",
        display_name="ada@example.com",
        identity_provider="google",
    )


def test_get_authenticated_user_falls_back_to_aca_shorthand_headers_for_microsoft():
    user = get_authenticated_user(
        headers={
            "X-MS-CLIENT-PRINCIPAL-IDP": "aad",
            "X-MS-CLIENT-PRINCIPAL-ID": "microsoft-oid-111",
            "X-MS-CLIENT-PRINCIPAL-NAME": "reviewer@example.com",
        }
    )

    assert user == AuthenticatedUser(
        user_id="microsoft-oid-111",
        display_name="reviewer@example.com",
        identity_provider="aad",
    )


def test_microsoft_and_google_users_do_not_share_quota_keys():
    microsoft = parse_client_principal(_encode_principal(("oid", "shared-value"), ("name", "MS")))
    google = parse_client_principal(
        _encode_principal(
            (_NAME_IDENTIFIER_CLAIM, "shared-value"),
            ("email", "g@example.com"),
            auth_typ="google",
        )
    )

    assert microsoft is not None
    assert google is not None
    assert microsoft.user_id == "shared-value"
    assert google.user_id == "google:shared-value"
    assert microsoft.user_id != google.user_id


def test_identity_provider_label():
    assert identity_provider_label("aad") == "Microsoft"
    assert identity_provider_label("google") == "Google"
    assert identity_provider_label(None) is None


def test_login_url_includes_provider_and_post_login_redirect():
    assert login_url("aad") == "/.auth/login/aad?post_login_redirect_uri=/"
    assert login_url("google") == "/.auth/login/google?post_login_redirect_uri=/"


def test_logout_url_includes_post_logout_redirect():
    assert logout_url() == "/.auth/logout?post_logout_redirect_uri=/"


def test_identity_required_false_in_dev_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUOTA_DEV_MODE", "1")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "prodaccount")

    assert identity_required() is False


def test_identity_required_true_when_storage_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUOTA_DEV_MODE", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "prodaccount")

    assert identity_required() is True
