"""Check installed Python packages against the project's license rule."""

import json
import re
import subprocess  # noqa: S404
import sys

PERMISSIVE = re.compile(
    r"\b(MIT|BSD|Apache|ISC|PSF|Python Software Foundation|Zlib|0BSD|Unlicense|CC0)\b",
    re.IGNORECASE,
)
COPYLEFT = re.compile(r"GPL|General Public|Mozilla|MPL|EPL|CDDL", re.IGNORECASE)

# The named exceptions recorded in docs/design/architecture.md. Each needs the
# maintainer's approval, and each must stay unmodified.
MPL_EXCEPTIONS = frozenset({"pathspec", "certifi", "hypothesis"})


def find_problems(packages: list[dict[str, str]]) -> list[str]:
    """Return a line for each package whose license isn't allowed."""
    problems = []
    for package in packages:
        name, license_name = package["Name"], package["License"]
        if name.lower() in MPL_EXCEPTIONS:
            continue
        if COPYLEFT.search(license_name) or not PERMISSIVE.search(license_name):
            problems.append(f"{name}: {license_name}")
    return problems


def main() -> int:
    """Print the license report, then fail on any problem."""
    report = subprocess.run(
        [  # noqa: S607
            "pip-licenses",
            "--format=json",
            "--from=mixed",
            "--python",
            sys.executable,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    packages = json.loads(report)
    problems = find_problems(packages)
    print(f"Checked {len(packages)} packages.")
    for problem in problems:
        print(f"Not allowed: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
