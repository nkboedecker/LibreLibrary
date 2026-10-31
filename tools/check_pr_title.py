"""Check that a pull request title is a Conventional Commit."""

import re
import sys

TYPES = "build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test"
TITLE = re.compile(rf"^({TYPES})(\([a-z0-9-]+\))?!?: \S.*$")


def is_valid_title(title: str) -> bool:
    """Return whether the title follows Conventional Commits."""
    return TITLE.match(title) is not None


def main() -> int:
    """Check the title given as the first argument."""
    if len(sys.argv) != 2:
        print("usage: check_pr_title.py TITLE")
        return 2
    if is_valid_title(sys.argv[1]):
        return 0
    print(f"Not a Conventional Commit title. Allowed types: {TYPES}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
