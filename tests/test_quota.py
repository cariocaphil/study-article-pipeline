"""Tests for src/utils/quota.py."""

import pytest

from src.utils.quota import (
    QuotaExceededError,
    QuotaUnavailableError,
    consume_generation,
    get_remaining,
    quota_enabled,
    reset_dev_quota_for_tests,
)


@pytest.fixture(autouse=True)
def dev_quota_env(monkeypatch):
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


def test_quota_enabled_in_dev_mode(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)

    assert quota_enabled() is True


def test_invalid_daily_quota_raises(monkeypatch):
    monkeypatch.setenv("DAILY_QUOTA", "0")

    with pytest.raises(QuotaUnavailableError):
        get_remaining("user-e")
