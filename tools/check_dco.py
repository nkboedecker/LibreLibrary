"""Check that each commit in a range has a human Signed-off-by line."""

import re
import subprocess  # noqa: S404
import sys

SIGN_OFF = re.compile(r"^Signed-off-by: (.+) <[^>]+@[^>]+>$", re.MULTILINE)
AGENT_NAMES = re.compile(r"\b(claude|copilot|chatgpt|codex|gemini|cursor)\b", re.I)


def has_human_sign_off(message: str) -> bool:
    """Return whether the message has a sign-off that isn't an AI tool's."""
    return any(not AGENT_NAMES.search(name) for name in SIGN_OFF.findall(message))


def main() -> int:
    """Check the commits in the range given as the first argument."""
    if len(sys.argv) != 2:
        print("usage: check_dco.py BASE..HEAD")
        return 2
    shas = subprocess.run(
        ["git", "rev-list", "--no-merges", sys.argv[1]],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    failed = 0
    for sha in shas:
        message = subprocess.run(
            ["git", "log", "-1", "--format=%B", sha],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if not has_human_sign_off(message):
            print(f"{sha}: missing a human Signed-off-by line")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
