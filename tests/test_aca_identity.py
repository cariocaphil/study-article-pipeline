"""Tests for src/utils/aca_identity.py."""

import base64
import json

from src.utils.aca_identity import (
    AuthenticatedUser,
    get_authenticated_user,
    identity_required,
    parse_client_principal,
)


def _encode_principal(*claims: tuple[str, str], auth_typ: str = "aad") -> str:
    payload = {
        "auth_typ": auth_typ,
        "claims": [{"typ": typ, "val": val} for typ, val in claims],
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def test_parse_client_principal_reads_oid_and_name():
    header = _encode_principal(
        ("oid", "user-123"),
        ("name", "Ada Lovelace"),
    )

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(user_id="user-123", display_name="Ada Lovelace")


def test_parse_client_principal_falls_back_to_sub_for_google():
    header = _encode_principal(
        ("sub", "google-sub-456"),
        ("email", "ada@example.com"),
        auth_typ="google",
    )

    user = parse_client_principal(header)

    assert user == AuthenticatedUser(user_id="google-sub-456", display_name="ada@example.com")


def test_parse_client_principal_returns_none_for_invalid_header():
    assert parse_client_principal(None) is None
    assert parse_client_principal("not-base64") is None


def test_get_authenticated_user_uses_dev_bypass(monkeypatch):
    monkeypatch.setenv("QUOTA_DEV_MODE", "1")
    monkeypatch.setenv("QUOTA_DEV_USER", "local-dev")

    user = get_authenticated_user(headers={})

    assert user == AuthenticatedUser(user_id="local-dev", display_name="local-dev")


def test_get_authenticated_user_reads_aca_header():
    header = _encode_principal(("oid", "aca-user"), ("name", "Reviewer"))
    user = get_authenticated_user(headers={"X-MS-CLIENT-PRINCIPAL": header})

    assert user == AuthenticatedUser(user_id="aca-user", display_name="Reviewer")


def test_identity_required_false_in_dev_mode(monkeypatch):
    monkeypatch.setenv("QUOTA_DEV_MODE", "1")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "prodaccount")

    assert identity_required() is False


def test_identity_required_true_when_storage_configured(monkeypatch):
    monkeypatch.delenv("QUOTA_DEV_MODE", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "prodaccount")

    assert identity_required() is True
