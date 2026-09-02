"""Daily per-user generation quotas backed by Azure Table Storage."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_dev_counts: dict[tuple[str, str], int] = {}


class QuotaExceededError(ValueError):
    pass


class QuotaUnavailableError(RuntimeError):
    pass


def _dev_mode_enabled() -> bool:
    return os.getenv("QUOTA_DEV_MODE", "").strip() == "1"


def _daily_quota() -> int:
    raw = os.getenv("DAILY_QUOTA", "3").strip()
    try:
        quota = int(raw)
    except ValueError as exc:
        raise QuotaUnavailableError(f"Invalid DAILY_QUOTA value: {raw!r}") from exc
    if quota < 1:
        raise QuotaUnavailableError("DAILY_QUOTA must be at least 1")
    return quota


def _utc_date_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def quota_enabled() -> bool:
    if _dev_mode_enabled():
        return True
    return bool(
        os.getenv("AZURE_STORAGE_ACCOUNT", "").strip() and os.getenv("QUOTA_TABLE_NAME", "").strip()
    )


def _table_client():
    from azure.data.tables import TableClient
    from azure.identity import DefaultAzureCredential

    account = os.environ["AZURE_STORAGE_ACCOUNT"].strip()
    table_name = os.environ["QUOTA_TABLE_NAME"].strip()
    endpoint = f"https://{account}.table.core.windows.net"
    credential = DefaultAzureCredential()
    return TableClient(endpoint=endpoint, table_name=table_name, credential=credential)


def get_remaining(user_id: str) -> int:
    daily_quota = _daily_quota()
    row_key = _utc_date_key()

    if _dev_mode_enabled():
        used = _dev_counts.get((user_id, row_key), 0)
        return max(0, daily_quota - used)

    from azure.core.exceptions import ResourceNotFoundError

    table = _table_client()
    try:
        entity = table.get_entity(partition_key=user_id, row_key=row_key)
        used = int(entity.get("count", 0))
    except ResourceNotFoundError:
        used = 0

    return max(0, daily_quota - used)


def consume_generation(user_id: str, *, max_attempts: int = 5) -> None:
    """Reserve one daily generation slot for the user.

    Raises QuotaExceededError when the daily limit is reached.
    Raises QuotaUnavailableError when quota storage cannot be reached.
    """
    daily_quota = _daily_quota()
    row_key = _utc_date_key()

    if _dev_mode_enabled():
        key = (user_id, row_key)
        used = _dev_counts.get(key, 0)
        if used >= daily_quota:
            raise QuotaExceededError("Daily generation limit reached.")
        _dev_counts[key] = used + 1
        return

    from azure.core import MatchConditions
    from azure.core.exceptions import (
        ResourceExistsError,
        ResourceModifiedError,
        ResourceNotFoundError,
    )
    from azure.data.tables import UpdateMode

    table = _table_client()

    for _ in range(max_attempts):
        try:
            entity = table.get_entity(partition_key=user_id, row_key=row_key)
            used = int(entity.get("count", 0))
            if used >= daily_quota:
                raise QuotaExceededError("Daily generation limit reached.")

            entity["count"] = used + 1
            table.update_entity(
                entity,
                mode=UpdateMode.REPLACE,
                etag=entity.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
            return
        except ResourceNotFoundError:
            try:
                table.create_entity(
                    {
                        "PartitionKey": user_id,
                        "RowKey": row_key,
                        "count": 1,
                    }
                )
                return
            except ResourceExistsError:
                continue
        except ResourceModifiedError:
            continue

    raise QuotaUnavailableError("Could not reserve a generation slot. Please try again.")


def reset_dev_quota_for_tests() -> None:
    _dev_counts.clear()
