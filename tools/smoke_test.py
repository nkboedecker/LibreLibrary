"""Start the image, wait until it is healthy, and confirm it isn't root."""

import subprocess  # noqa: S404
import sys
import time

CONTAINER = "librelibrary-smoke"
TIMEOUT_SECONDS = 60


def docker(*args: str) -> str:
    """Run a Docker command and return its output."""
    return subprocess.run(
        ["docker", *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    """Run the smoke test against the image named in the first argument."""
    image = sys.argv[1] if len(sys.argv) > 1 else "librelibrary:dev"
    docker("run", "--detach", "--name", CONTAINER, image)
    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        health = "starting"
        while time.monotonic() < deadline:
            health = docker(
                "inspect", "--format", "{{.State.Health.Status}}", CONTAINER
            )
            if health != "starting":
                break
            time.sleep(1)
        uid = docker("exec", CONTAINER, "id", "-u")
        print(f"health={health} uid={uid}")
        return 0 if health == "healthy" and uid != "0" else 1
    finally:
        docker("rm", "--force", CONTAINER)


if __name__ == "__main__":
    raise SystemExit(main())
