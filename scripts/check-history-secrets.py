#!/usr/bin/env python3
"""Scan all reachable Git patches; report locations, never credential contents.

This is a bounded detector for our credential names and provider token formats,
not a claim to detect every possible secret. Exact reviewed test literals are
allowed only in their original files; arbitrary test files are still scanned.
"""
import hashlib
import re
import subprocess
import sys

TOKEN = re.compile(r"(?<![A-Za-z0-9_])(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})")
ASSIGNMENT = re.compile(
    r"(?:^|[\s,(])(?:export\s+)?(?:USTC_API(?:_KEY)?|TEACHER_PASSWORD|SESSION_SECRET)"
    r"\s*=\s*(?:\"([^\"\n]*)\"|'([^'\n]*)'|([^\s,;)]+))"
)
# Exact pre-existing fixtures for redaction, provider routing and fake credential vaults.
FIXTURES = {
    "services/api/tests/test_auth_login.py": {
        "f2d927e8aed50a30742ed8a82dcd7ea6c42df097c7c3429a0dfaef30b3b4d9fd",
        "4057fc32861c55428e127ae68575b48f2e0a63ea1b2bf760591d601d309ddb98",
        "db128b9cac1d76e531e68861e3b7faba8a07483303d01657741ef6d486a1a900",
        "344926b04626260f57fc9240debc249450c4b3073bab87937c7758e1be949285",
    },
    "services/api/tests/test_credential_vault.py": {
        "4656a1e9d79706e47dc2a55491d022c421f539737a2f9728c75710127289d3b4",
        "d79ec8febbff575fb67a91e578282272d671c32dc67620d1415e4f7b265f7bc1",
        "35c6a357ed036c3d1d5bab1ff2ef8b11489f0e45cbc6f694652c4887433db8cb",
    },
    "services/api/tests/test_db_models.py": {"744ffbc09ead9000eebd9196f1b6c577014d487a6e39f5514b9f17884a0ab03e"},
    "services/api/tests/test_gateways.py": {
        "c17bf10efff913539bd1dc85af67ba8ac6f72f93b049a47346aa8ada21c3d218",
        "1923f665927132505277ebc362369d83522ec948ca77600f0090716f7974e812",
    },
    "services/api/tests/test_model_routing.py": {"930bbdc51b6aed5c2a5678fd6e28dee7a05e8a4b643cfc0b4427c3efb86c0d94"},
}


def suspicious(line: str, path: str) -> bool:
    for token in TOKEN.finditer(line):
        if hashlib.sha256(token[0].encode()).hexdigest() not in FIXTURES.get(path, set()):
            return True
    for match in ASSIGNMENT.finditer(line):
        value = next(v for v in match.groups() if v is not None)
        if not value or value in {"None", "null"} or value.startswith(("$", "${", "<")):
            continue
        if hashlib.sha256(value.encode()).hexdigest() in FIXTURES.get(path, set()):
            continue
        return True
    return False


def main() -> int:
    process = subprocess.Popen(
        ["git", "log", "--all", "--format=commit %H", "-p", "--no-ext-diff"],
        stdout=subprocess.PIPE, text=True, errors="replace",
    )
    assert process.stdout is not None
    commit, path = "unknown", "unknown"
    findings = set()
    for line in process.stdout:
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith("diff --git "):
            path = line.rstrip().split(" b/", 1)[-1]
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if suspicious(line[1:], path):
                findings.add((commit, path))
    status = process.wait()
    for commit, path in sorted(findings):
        print(f"Potential credential: {commit[:12]} {path}", file=sys.stderr)
    if findings or status:
        return 1
    print("History credential scan passed (all reachable commits).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
