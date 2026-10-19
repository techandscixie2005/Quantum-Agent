"""Collect safe synthetic trial evidence, excluding private browser/network traces.

Runtime manifests, invitations, DSNs and credentials stay in the private test
directory. Text artifacts matching a runtime credential are omitted entirely.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path


def collect(source: Path, destination: Path, source_manifest: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    private_values = [
        manifest["database_url"],
        "backend-live-provider-fixture-key",
        base64.urlsafe_b64encode(bytes(range(32))).decode(),
        *(
            actor["classroom_access_token"]
            for actors in manifest["actors"].values()
            for actor in actors
        ),
    ]
    destination.mkdir(parents=True, exist_ok=True)
    excluded: list[dict[str, str]] = []
    candidates = [source / name for name in ("results.json", "api.log", "web.log", "provider.log")]
    candidates.extend((source / "browser").rglob("*.png"))
    for file in candidates:
        if not file.is_file():
            continue
        relative = file.relative_to(source)
        if file.suffix != ".png":
            text = file.read_text(encoding="utf-8", errors="replace")
            if any(value and value in text for value in private_values):
                excluded.append({"path": str(relative), "reason": "runtime credential in text"})
                continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
    safe = {
        key: manifest[key]
        for key in (
            "fixture_label",
            "run_id",
            "course_id",
            "edition_id",
            "database_mode",
            "api_url",
            "provider_url",
            "web_url",
            "api_workers",
            "credential_vault",
        )
    }
    safe.update(
        {
            "model_test_double": True,
            "actual_classroom_results": False,
            "actual_teacher_approval": False,
        }
    )
    (destination / "runtime-manifest.redacted.json").write_text(
        json.dumps(safe, indent=2),
        encoding="utf-8",
    )
    shutil.copyfile(source_manifest, destination / "source-manifest.json")
    (destination / "exclusions.json").write_text(
        json.dumps(
            {
                "always_excluded": [
                    "manifest.json: database DSN and single-use runtime invitations",
                    "browser/network traces: may contain login bodies, cookies or auth headers",
                    "error-context.md: may include sensitive form state or network context",
                ],
                "additional_exclusions": excluded,
                "private_originals_retained_at": str(source),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "collected": True,
                "excluded_text_artifacts": len(excluded),
                "actual_classroom_results": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    args = parser.parse_args()
    collect(args.source, args.destination, args.source_manifest)
