"""Tests for src/utils/quota.py."""

from unittest.mock import MagicMock

import pytest

from src.utils.quota import (
    QuotaExceededError,
    QuotaUnavailableError,
    _as_int,
    consume_generation,
    get_remaining,
    quota_enabled,
    reset_dev_quota_for_tests,
)


@pytest.fixture(autouse=True)
def dev_quota_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUOTA_DEV_MODE", "1")
    monkeypatch.setenv("QUOTA_DEV_USER", "quota-user")
    monkeypatch.setenv("DAILY_QUOTA", "2")
    reset_dev_quota_for_tests()
    yield
    reset_dev_quota_for_tests()


def test_get_remaining_starts_at_daily_quota():
    assert get_remaining("user-a") == 2


def test_consume_generation_decrements_remaining():
    consume_generation("user-a")

    assert get_remaining("user-a") == 1


def test_consume_generation_raises_when_quota_exceeded():
    consume_generation("user-b")
    consume_generation("user-b")

    with pytest.raises(QuotaExceededError):
        consume_generation("user-b")


def test_quota_is_per_user():
    consume_generation("user-c")
    consume_generation("user-c")

    assert get_remaining("user-c") == 0
    assert get_remaining("user-d") == 2


def test_quota_enabled_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)

    assert quota_enabled() is True


def test_invalid_daily_quota_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAILY_QUOTA", "0")

    with pytest.raises(QuotaUnavailableError):
        get_remaining("user-e")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 0),
        (False, 0),
        (3, 3),
        (True, 0),
        (False, 0),
        ("7", 7),
        ("not-a-number", 0),
        (3.5, 0),
        (None, 0),
        ([], 0),
    ],
)
def test_as_int_coerces_table_entity_values(value: object, expected: int) -> None:
    assert _as_int(value) == expected


def test_get_remaining_uses_as_int_for_table_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUOTA_DEV_MODE", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    monkeypatch.setenv("QUOTA_TABLE_NAME", "quota")
    monkeypatch.setenv("DAILY_QUOTA", "5")

    table = MagicMock()
    table.get_entity.return_value = {"count": "2"}
    monkeypatch.setattr("src.utils.quota._table_client", lambda: table)

    assert get_remaining("user-a") == 3


def test_consume_generation_uses_as_int_for_table_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUOTA_DEV_MODE", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    monkeypatch.setenv("QUOTA_TABLE_NAME", "quota")
    monkeypatch.setenv("DAILY_QUOTA", "5")

    entity = MagicMock()

    def entity_get(key: object, default: object = 0) -> object:
        return True if key == "count" else default

    entity.get.side_effect = entity_get
    entity.metadata = {"etag": "etag-1"}
    table = MagicMock()
    table.get_entity.return_value = entity
    monkeypatch.setattr("src.utils.quota._table_client", lambda: table)

    consume_generation("user-a")

    entity.__setitem__.assert_called_with("count", 1)
    table.update_entity.assert_called_once()
