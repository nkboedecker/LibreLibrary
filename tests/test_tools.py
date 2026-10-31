"""Test the project's check scripts."""

import pytest

from check_dco import has_human_sign_off
from check_licenses import find_problems
from check_pr_title import is_valid_title


@pytest.mark.parametrize(
    "title",
    ["feat: add loans", "fix(api): reject bad ISBNs", "chore(deps)!: bump Python"],
)
def test_valid_pr_titles(title: str) -> None:
    """Conventional Commit titles pass."""
    assert is_valid_title(title)


@pytest.mark.parametrize(
    "title", ["Add loans", "feat add loans", "feat: ", "unknown: add loans"]
)
def test_invalid_pr_titles(title: str) -> None:
    """Other titles fail."""
    assert not is_valid_title(title)


def test_sign_off_is_required() -> None:
    """A commit needs a Signed-off-by line."""
    assert has_human_sign_off("fix: a\n\nSigned-off-by: A Person <a@example.com>\n")
    assert not has_human_sign_off("fix: a\n")


def test_agents_cannot_sign_off() -> None:
    """A sign-off by an AI tool doesn't count."""
    message = "fix: a\n\nSigned-off-by: Claude <noreply@anthropic.com>\n"

    assert not has_human_sign_off(message)


def test_license_check_allows_permissive_and_named_exceptions() -> None:
    """Permissive licenses and the named MPL-2.0 packages pass."""
    packages = [
        {"Name": "a", "License": "MIT License"},
        {"Name": "b", "License": "Apache-2.0"},
        {"Name": "certifi", "License": "Mozilla Public License 2.0 (MPL 2.0)"},
    ]

    assert find_problems(packages) == []


def test_license_check_flags_copyleft_and_unknown() -> None:
    """Unnamed MPL-2.0, GPL, and unknown licenses fail."""
    packages = [
        {"Name": "a", "License": "Mozilla Public License 2.0 (MPL 2.0)"},
        {"Name": "b", "License": "GNU General Public License v3 (GPLv3)"},
        {"Name": "c", "License": "UNKNOWN"},
    ]

    assert len(find_problems(packages)) == 3
