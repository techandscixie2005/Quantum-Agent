"""Capture byte-exact source, referenced local evidence and explicit raw logs.

python scripts/capture-review-snapshot.py capture --output outputs/review/<new-name> \
  --raw-log-root outputs/classroom-20261019
python scripts/capture-review-snapshot.py verify outputs/review/<new-name>

Dependencies, virtual disks, Git internals and credentials are excluded explicitly.
This is a local review bundle, never deployment or classroom attestation.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OMIT_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".sites-runtime"}
OMIT_SUFFIXES = {".pem", ".key", ".vhd", ".vhdx", ".sqlite", ".db"}
SECRET_NAMES = (
    "USTC_API", "EMBEDDING_API_KEY", "SESSION_VAULT_KEY", "POSTGRES_PASSWORD",
    "POSTGRES_PASSWORD_URLENCODED", "NEO4J_PASSWORD", "REDIS_PASSWORD",
)
LINK = re.compile(r"\]\((<[^>]+>|[^)]+)\)")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def exclusion(path: Path) -> str | None:
    name = path.name.lower()
    if any(part in OMIT_PARTS for part in path.parts):
        return "dependency, cache or Git internals"
    if name.startswith(".env") and name != ".env.example":
        return "runtime environment credentials"
    if name in {"private.env", "storage-state.json", "credentials.json", "auth.json"}:
        return "runtime credentials or authenticated browser state"
    if "test-results" in path.parts and name == "manifest.json":
        return "fixture runtime manifest contains invitations and database credentials"
    if name == ".dev.vars" or path.suffix.lower() in OMIT_SUFFIXES:
        return "private key, database or virtual disk"
    if path.is_symlink():
        return "symlinks require explicit review; no external targets followed"
    return None


def source_paths() -> set[Path]:
    names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return {ROOT / os.fsdecode(name) for name in names.split(b"\0") if name}


def collect(
    log_roots: list[Path], base_revision: str,
) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    paths = source_paths()
    omitted: list[dict[str, str]] = []
    # Resolve local Markdown links, including evidence omitted by Git ignore rules.
    for path in list(paths):
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        for target in LINK.findall(path.read_text(encoding="utf-8", errors="replace")):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "data:")):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.is_relative_to(ROOT):
                omitted.append({"reference": target, "from": str(path.relative_to(ROOT)),
                                "reason": "outside repository; not copied"})
            elif candidate.is_file():
                paths.add(candidate)
            elif not candidate.exists():
                omitted.append({"reference": target, "from": str(path.relative_to(ROOT)),
                                "reason": "missing historical/local reference"})
    blobs: dict[str, bytes] = {}
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        reason = exclusion(path)
        if reason or not path.is_file():
            omitted.append({"path": relative, "reason": reason or "deleted or non-file"})
            continue
        blobs["source/" + relative] = path.read_bytes()
    for requested in log_roots:
        directory = requested.resolve()
        if not directory.is_relative_to(ROOT) or not directory.is_dir():
            raise ValueError("raw log roots must be existing directories within this workspace")
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            reason = exclusion(path)
            if reason:
                omitted.append({"path": relative, "reason": reason})
                continue
            if path.suffix.lower() not in {".log", ".txt", ".json", ".xml", ".png"}:
                omitted.append({"path": relative, "reason": "not an explicit raw-log format"})
                continue
            blobs["raw-evidence/" + relative] = path.read_bytes()
    blobs["review/git-diff.patch"] = git("diff", "--binary", base_revision)
    blobs["review/git-status.txt"] = git("status", "--short")
    # Exact matching is intentionally bounded; do not claim general secret discovery.
    secrets = [value.encode() for name in SECRET_NAMES
               if len(value := os.environ.get(name, "")) >= 12]
    for name, blob in blobs.items():
        if any(secret in blob for secret in secrets):
            raise ValueError(f"known environment credential detected in {name}; bundle refused")
    return blobs, omitted


def capture(output: Path, log_roots: list[Path], max_bytes: int, compare_to: str) -> None:
    output = output.resolve()
    if not output.is_relative_to(ROOT / "outputs"):
        raise ValueError("write review bundles under the ignored workspace outputs directory")
    if output.exists():
        raise ValueError("refusing to overwrite a prior review bundle")
    base = git("rev-parse", "--verify", compare_to + "^{commit}").decode().strip()
    listed_before = source_paths()
    blobs, omitted = collect(log_roots, base)
    size = sum(map(len, blobs.values()))
    if size > max_bytes:
        raise ValueError("snapshot exceeds explicit size limit; nothing was silently truncated")
    # Files may be edited by another agent. Refuse an internally inconsistent capture.
    for name, blob in blobs.items():
        if name.startswith("source/") and (ROOT / name[7:]).read_bytes() != blob:
            raise ValueError("source changed during capture; freeze edits and retry")
    if source_paths() != listed_before:
        raise ValueError("source file inventory changed during capture; freeze edits and retry")
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "source-and-evidence.tar.gz"
    entries: list[dict[str, Any]] = []
    with (
        archive.open("xb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as tar,
    ):
        for name, blob in sorted(blobs.items()):
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(blob))
            entries.append({"path": name, "bytes": len(blob), "sha256": sha(blob)})
    manifest: dict[str, Any] = {
        "schema_version": "reviewable-source-snapshot/1",
        "kind": "local_snapshot_not_deployment_or_classroom_attestation",
        "captured_at": datetime.now(UTC).isoformat(),
        "base_revision": base,
        "head_revision": git("rev-parse", "HEAD").decode().strip(),
        "branch": git("branch", "--show-current").decode().strip(),
        "dirty": bool(git("status", "--porcelain")),
        "archive": archive.name, "archive_sha256": sha(archive.read_bytes()),
        "uncompressed_bytes": size, "files": entries, "omissions": omitted,
        "source_tree_sha256": sha(json.dumps(
            [item for item in entries if item["path"].startswith("source/")],
            sort_keys=True, separators=(",", ":"),
        ).encode()),
        "raw_log_roots": [str(path.resolve().relative_to(ROOT)) for path in log_roots],
        "excluded_categories": [
            "Git internals; dependencies and caches; generated build directories",
            "runtime environment files and private credentials; populated databases",
            "WSL virtual disks; downloaded runtime archives and container layers",
            "ignored outputs except local referenced files and explicit raw-log roots",
            "external/local references outside this repository; missing historical references",
        ],
        "credential_handling": "Environment files/keys/databases excluded; known configured "
                               "environment credential bytes checked; not an exhaustive detector.",
        "historical_limit": "Earlier hash-only source manifests do not recreate missing earlier "
                            "file bytes. This archive captures the current source in full.",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verify(output)


def verify(output: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    archive = output / manifest["archive"]
    if sha(archive.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("archive digest mismatch")
    expected = {item["path"]: item for item in manifest["files"]}
    seen = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("unexpected, duplicate or non-file archive member")
            stream = tar.extractfile(member)
            assert stream is not None
            data = stream.read()
            item = expected[member.name]
            if len(data) != item["bytes"] or sha(data) != item["sha256"]:
                raise ValueError("member digest mismatch")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("archive is incomplete")
    print(json.dumps({"manifest": str(output / "manifest.json"), "verified_files": len(seen),
                      "archive_sha256": manifest["archive_sha256"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("capture")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--raw-log-root", action="append", type=Path, default=[])
    create.add_argument("--max-bytes", type=int, default=2 * 1024**3)
    create.add_argument("--compare-to", default="HEAD", help="Git commit/ref for the review diff")
    check = commands.add_parser("verify")
    check.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.output, args.raw_log_root, args.max_bytes, args.compare_to)
    else:
        verify(args.output)


if __name__ == "__main__":
    main()
