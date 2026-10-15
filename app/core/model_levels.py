"""Canonical user-selectable model levels shared by API and agent graphs."""

from typing import Literal, cast

ModelLevel = Literal["low", "medium", "high"]


def normalize_model_level(level: str | None = "medium") -> ModelLevel:
    value = (level or "medium").strip().lower() or "medium"
    if value not in ("low", "medium", "high"):
        raise ValueError("model_level must be low, medium or high")
    return cast(ModelLevel, value)
