"""Write the OpenAPI spec, or check that the committed copy is current."""

import json
import sys
from pathlib import Path

from librelibrary.app import create_app

SPEC_PATH = Path(__file__).parent.parent / "openapi" / "openapi.json"


def render_spec() -> str:
    """Return the generated spec as stable, readable JSON."""
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    """Write the spec, or compare it to the committed copy with --check."""
    spec = render_spec()
    if "--check" in sys.argv:
        if not SPEC_PATH.exists() or SPEC_PATH.read_text() != spec:
            print("openapi/openapi.json is out of date. Run: nox -s openapi_update")
            return 1
        return 0
    SPEC_PATH.parent.mkdir(exist_ok=True)
    SPEC_PATH.write_text(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
