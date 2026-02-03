#!/usr/bin/env python3
"""
Test script: exercises all MITRE API endpoints.

API endpoints:
- GET /api/mitre/version  → latest x_mitre_version
- GET /api/mitre/         → retrieve MITRE content as JSON
- PUT /api/mitre/{x_mitre_version}  → replace MITRE for given version
- PUT /api/mitre/         → create new MITRE entry (body: bundle; version from spec_version)

Run with backend server up (e.g. uvicorn app.main:app --reload).
"""
import json
import os
import sys

import requests
from pymongo import MongoClient

from app.config import settings

# Paths and DB constants (match app.db.mongo)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STIX_PATH = os.path.join(SCRIPT_DIR, "arifacts", "enterprise-attack-1.0.json")
STIX_EDITED_PATH = os.path.join(SCRIPT_DIR, "arifacts", "enterprise-attack-1.0.json")
API_BASE = f"{settings.mitre_api_base}/api/mitre"
DATABASE_NAME = "mitre_db"
COLLECTIONS = ("current_schema", "mitre_entities", "mitre_documents")

FAILED = []


def drop_collections() -> None:
    """Delete all MITRE collections so tests start from a clean state."""
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[DATABASE_NAME]
        for name in COLLECTIONS:
            db[name].drop()
        print("Dropped collections: " + ", ".join(COLLECTIONS))
    finally:
        client.close()


def load_payload(path: str):
    if not os.path.isfile(path):
        print(f"STIX file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ok(name: str, resp: requests.Response, want_status: int | None = None) -> bool:
    if want_status is not None and resp.status_code != want_status:
        print(f"  FAIL {name}: got status {resp.status_code}, want {want_status}")
        FAILED.append(name)
        return False
    if not resp.ok and want_status is None:
        print(f"  FAIL {name}: status {resp.status_code} -> {resp.text[:200]}")
        FAILED.append(name)
        return False
    print(f"  OK   {name}")
    return True


def main() -> None:
    drop_collections()

    payload = load_payload(STIX_PATH)
    payload_edited = load_payload(STIX_EDITED_PATH)
    # version_from_bundle = payload.get("x_mitre_version", "14.1")
    version_from_bundle = payload["objects"][0]["x_mitre_version"]
    spec_version = payload["objects"][0]["spec_version"]

    print("\nMITRE API tests")
    print("=" * 50)

    # --- GET /api/mitre/version ---
    print("\n1. GET /api/mitre/version")
    r = requests.get(f"{API_BASE}/version")
    if r.status_code == 404:
        print("  OK   GET version (no data yet -> 404)")
    elif r.ok:
        data = r.json()
        print(f"  OK   GET version -> x_mitre_version={data.get('x_mitre_version')}")
    else:
        ok("GET version", r)

    # --- GET /api/mitre/ ---
    print("\n2. GET /api/mitre/ (content)")
    r = requests.get(f"{API_BASE}/")
    if r.status_code == 404:
        print("  OK   GET content (no data yet -> 404)")
    elif r.ok:
        data = r.json()
        print(f"  OK   GET content -> version={data.get('x_mitre_version')}, objects={len(data.get('content', {}).get('objects', []))}")
    else:
        ok("GET content", r)

    # --- PUT /api/mitre/ (create) ---
    print("\n3. PUT /api/mitre/ (create new entry)")
    r = requests.put(f"{API_BASE}/", json=payload)
    if not ok("PUT create", r, 201):
        print(f"     Response: {r.text[:300]}")
    else:
        data = r.json()
        print(f"     -> status={data.get('status')}, x_mitre_version={data.get('x_mitre_version')}")

    # --- GET /api/mitre/version (should return created version) ---
    print("\n4. GET /api/mitre/version (after create)")
    r = requests.get(f"{API_BASE}/version")
    if ok("GET version", r, 200):
        data = r.json()
        print(f"     -> x_mitre_version={data.get('x_mitre_version')} (from spec_version={spec_version})")

    # --- GET /api/mitre/ (content) ---
    print("\n5. GET /api/mitre/ (content after create)")
    r = requests.get(f"{API_BASE}/")
    if ok("GET content", r, 200):
        data = r.json()
        print(f"     -> version={data.get('x_mitre_version')}, objects={len(data.get('content', {}).get('objects', []))}")

    # --- PUT /api/mitre/ again (duplicate -> 409) ---
    print("\n6. PUT /api/mitre/ (same version again -> 409)")
    r = requests.put(f"{API_BASE}/", json=payload)
    ok("PUT create duplicate", r, 409)

    # --- PUT /api/mitre/{x_mitre_version} (replace/update) ---
    # print("\n7. PUT /api/mitre/{x_mitre_version} (replace)")
    # url = f"{API_BASE}/{version_from_bundle}"
    # r = requests.put(url, json=payload_edited)
    # if not ok("PUT replace", r, 200):
    #     print(f"     Response: {r.text[:300]}")
    # else:
    #     data = r.json()
    #     print(f"     -> status={data.get('status')}, x_mitre_version={data.get('x_mitre_version')}")

    # --- GET /api/mitre/version (should be updated version) ---
    print("\n8. GET /api/mitre/version (after replace)")
    r = requests.get(f"{API_BASE}/version")
    if ok("GET version", r, 200):
        data = r.json()
        print(f"     -> x_mitre_version={data.get('x_mitre_version')} (expected {version_from_bundle})")

    # --- GET /api/mitre/ (content after replace) ---
    print("\n9. GET /api/mitre/ (content after replace)")
    r = requests.get(f"{API_BASE}/")
    if ok("GET content", r, 200):
        data = r.json()
        print(f"     -> version={data.get('x_mitre_version')}, objects={len(data.get('content', {}).get('objects', []))}")

    # --- Summary ---
    print("\n" + "=" * 50)
    if FAILED:
        print(f"FAILED: {len(FAILED)} test(s) -> {FAILED}")
        sys.exit(1)
    print("All API tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
