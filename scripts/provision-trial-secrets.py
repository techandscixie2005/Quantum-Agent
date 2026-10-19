"""Provision private, persistent credentials for an isolated synthetic trial stack.

Never use this generated provider placeholder for a real classroom deployment.
The provider must be the local HTTP test stub. Existing secrets are never reset.
"""

import argparse
import base64
import os
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = args.directory / "private.env"
    values = {
        "POSTGRES_PASSWORD": secrets.token_hex(20),
        "NEO4J_PASSWORD": secrets.token_hex(20),
        "REDIS_PASSWORD": secrets.token_hex(20),
        "SESSION_VAULT_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "USTC_API": "synthetic-provider-fixture-not-a-real-key",
        "API_ENVIRONMENT": "production",
        "POSTGRES_DB": "quantum_backend_live",
        "POSTGRES_USER": "quantum_agent",
    }
    values["POSTGRES_PASSWORD_URLENCODED"] = values["POSTGRES_PASSWORD"]
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print("Created private synthetic-trial credentials; values were not printed.")


if __name__ == "__main__":
    main()
