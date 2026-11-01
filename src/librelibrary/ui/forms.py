"""Helpers for reading HTML forms, which send every field as text."""

from pydantic import ValidationError


def blank_to_none(value: str) -> str | None:
    """Trim a text field, and turn an empty one into None."""
    return value.strip() or None


def problems(error: ValidationError, labels: dict[str, str]) -> list[str]:
    """Describe which fields failed, without echoing what was typed."""
    fields = {str(item["loc"][0]) for item in error.errors() if item["loc"]}
    return [f"Check {labels.get(field, field)}." for field in sorted(fields)]
