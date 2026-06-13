from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class TransactionState(TypedDict):
    """State shared across the agent pipeline."""

    raw_transactions: list[dict]
    mapped_transactions: list[dict]
    categorized: list[dict]
    shariah_screened: list[dict]
    recurrence_groups: list[dict]
    insights: list[dict]
    profile_updates: dict
    errors: Annotated[list[str], operator.add]
    metadata: dict  # timing, token usage, model versions
