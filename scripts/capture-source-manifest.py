"""Record the local code snapshot used for automated checks, without reading secrets."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = [
    ".github",
    "app",
    "lib",
    "worker",
    "db",
    "tests",
    "scripts",
    "content",
    "services/api/quantum_agent",
    "services/api/tests",
    "services/api/alembic",
    "services/api/pyproject.toml",
    "services/api/uv.lock",
    "package.json",
    "package-lock.json",
    "compose.yaml",
    "vite.config.ts",
    "playwright.config.ts",
]


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, encoding="utf-8").strip()


def main() -> None:
    paths = sorted(
        set(
            git(
                "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SCOPES
            ).split("\0")
        )
    )
    files = [
        {"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
        for name in paths
        if (ROOT / name).is_file()
    ]
    canonical = "".join(f"{item['path']}\0{item['sha256']}\n" for item in files)
    print(
        json.dumps(
            {
                "kind": "local_source_snapshot_not_deployment_attestation",
                "base_revision": git("rev-parse", "HEAD"),
                "branch": git("branch", "--show-current"),
                "dirty": bool(git("status", "--porcelain")),
                "source_tree_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "files": files,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
