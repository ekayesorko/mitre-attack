#!/usr/bin/env python3
"""
Test script: call PUT /api/mitre/{x_mitre_version} with small_stix.json.
Run with backend server up (e.g. uvicorn app.main:app --reload).
"""
import json
import os
import sys
import requests

# Config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STIX_PATH = os.path.join(SCRIPT_DIR, "arifacts", "enterprise-attack-2.0.json")
BASE_URL = os.environ.get("MITRE_API_BASE", "http://localhost:8000")


def main() -> None:
    if not os.path.isfile(STIX_PATH):
        print(f"STIX file not found: {STIX_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(STIX_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Use version from bundle or default
    version = payload.get("x_mitre_version", "14.1")
    url = f"{BASE_URL}/api/mitre/"

    print(f"PUT {url}")
    print(f"Body: {STIX_PATH} ({len(json.dumps(payload))} chars)")

    resp = requests.put(url, json=payload)

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")

    if not resp.ok:
        sys.exit(1)

    data = resp.json()
    print(f"Result: {data.get('status')} x_mitre_version={data.get('x_mitre_version')}")


if __name__ == "__main__":
    main()
