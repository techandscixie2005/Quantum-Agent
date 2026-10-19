"""Archive nonignored source and fingerprint its exact bytes for a Linux trial.

Does not include Git internals, node_modules, environments or ignored outputs.
The SHA256 identifies a source snapshot, not a Git commit or a classroom result.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    output = root / "test-results" / "backend-live"
    output.mkdir(parents=True, exist_ok=True)
    names = sorted(
        set(
            subprocess.check_output(
                ["git", "-C", str(root), "ls-files", "-z", "-co", "--exclude-standard"],
            )
            .decode()
            .split("\0")
        )
        - {""}
    )
    digest = hashlib.sha256()
    count = 0
    with tarfile.open(output / "source-stage.tar", "w") as archive:
        for name in names:
            source = root / name
            if not source.exists():
                continue
            if source.is_symlink():
                raise ValueError("Source staging requires ordinary repository files")
            if not source.is_file():
                continue
            raw = source.read_bytes()
            digest.update(name.encode("utf-8") + b"\0" + str(len(raw)).encode() + b"\0" + raw)
            info = archive.gettarinfo(str(source), arcname=name)
            archive.addfile(info, io.BytesIO(raw))
            count += 1
    metadata = {
        "kind": "canonical-nonignored-source-snapshot-sha256",
        "sha256": digest.hexdigest(),
        "files": count,
        "classroom_evidence": False,
    }
    (output / "source-stage.json").write_text(json.dumps(metadata), encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
