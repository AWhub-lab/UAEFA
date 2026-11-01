#!/usr/bin/env python3
"""Create an ignored Streamlit secrets.toml from a service-account JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service_account_json", type=Path)
    parser.add_argument("--drive-root-id", required=True)
    parser.add_argument("--output", type=Path, default=Path(".streamlit/secrets.toml"))
    args = parser.parse_args()

    credentials = json.loads(args.service_account_json.read_text(encoding="utf-8"))
    payload = json.dumps(credentials, indent=2, ensure_ascii=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "[drive]\n"
        f'root_folder_id = "{args.drive_root_id}"\n'
        "service_account_json = '''\n"
        f"{payload}\n"
        "'''\n\n"
        "[access]\n"
        'password = "REPLACE_WITH_A_STRONG_PRIVATE_PASSWORD"\n',
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
