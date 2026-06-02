#!/usr/bin/env python3
"""
meraki_ap_config.py — Batch configure Meraki APs via the Dashboard API.

CSV format (all modes):
    serial, name, tags, network_name
    Q234-ABCD-0001, AP-Floor1, floor-1;building-a, HQ-Network
    Q234-ABCD-0002, AP-Floor2, floor-2;building-a, HQ-Network

    - serial       : required for all modes
    - name         : required for --add and --update
    - tags         : optional; semicolon-separated (e.g. floor-1;building-a)
    - network_name : required for --add

Usage examples:
    python meraki_ap_config.py --claim  --source aps.csv --token YOUR_TOKEN
    python meraki_ap_config.py --add    --source aps.csv --token YOUR_TOKEN
    python meraki_ap_config.py --update --source aps.csv --token YOUR_TOKEN
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from typing import Any

import requests

BASE_URL: str = "https://api.meraki.com/api/v1"
RATE_LIMIT_DELAY: float = 0.25  # seconds between API calls

# Type aliases
Row = dict[str, str]
Payload = dict[str, Any]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict[str, str]:
    return {
        "X-Cisco-Meraki-API-Key": token,
        "Content-Type": "application/json",
    }


def get(token: str, path: str, params: dict[str, str] | None = None) -> Any:
    """GET request; returns parsed JSON or raises on HTTP error."""
    resp = requests.get(f"{BASE_URL}{path}", headers=_headers(token), params=params)
    resp.raise_for_status()
    return resp.json()


def post(token: str, path: str, payload: Payload) -> Any:
    """POST request; returns parsed JSON or raises on HTTP error."""
    resp = requests.post(f"{BASE_URL}{path}", headers=_headers(token), json=payload)
    resp.raise_for_status()
    return resp.json()


def put(token: str, path: str, payload: Payload) -> Any:
    """PUT request; returns parsed JSON or raises on HTTP error."""
    resp = requests.put(f"{BASE_URL}{path}", headers=_headers(token), json=payload)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_org_id(token: str) -> str:
    """Return the first organization ID accessible with this token."""
    orgs: list[dict[str, Any]] = get(token, "/organizations")
    if not orgs:
        print("ERROR: No organizations found for this API token.", file=sys.stderr)
        sys.exit(1)
    if len(orgs) > 1:
        print(f"INFO: Multiple organizations found; using '{orgs[0]['name']}' ({orgs[0]['id']}).")
    return str(orgs[0]["id"])


def get_networks(token: str, org_id: str) -> dict[str, str]:
    """Return a dict mapping network name -> network ID."""
    networks: list[dict[str, Any]] = get(token, f"/organizations/{org_id}/networks")
    return {str(n["name"]): str(n["id"]) for n in networks}


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: set[str] = {"serial"}
ADD_REQUIRED_COLUMNS: set[str] = {"serial", "name", "network_name"}
UPDATE_REQUIRED_COLUMNS: set[str] = {"serial", "name"}


def load_csv(path: str, mode: str) -> list[Row]:
    """Load and validate the CSV file for the given mode."""
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows: list[Row] = [dict(row) for row in reader]
    except FileNotFoundError:
        print(f"ERROR: CSV file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not read CSV file: {e}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("ERROR: CSV file is empty.", file=sys.stderr)
        sys.exit(1)

    # Normalise column names (strip whitespace, lowercase)
    rows = [{k.strip().lower(): v.strip() for k, v in row.items()} for row in rows]
    columns: set[str] = set(rows[0].keys())

    required: set[str]
    if mode == "claim":
        required = REQUIRED_COLUMNS
    elif mode == "add":
        required = ADD_REQUIRED_COLUMNS
    else:  # update
        required = UPDATE_REQUIRED_COLUMNS

    missing: set[str] = required - columns
    if missing:
        print(
            f"ERROR: CSV is missing required column(s) for --{mode}: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        sys.exit(1)

    return rows


# ---------------------------------------------------------------------------
# Tag parsing helper
# ---------------------------------------------------------------------------

def parse_tags(raw: str) -> list[str]:
    """Split a semicolon-separated tag string into a clean list."""
    return [t.strip() for t in raw.split(";") if t.strip()]


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

def do_claim(token: str, rows: list[Row]) -> None:
    """Claim APs into the organization inventory (no network assignment)."""
    org_id: str = get_org_id(token)
    serials: list[str] = [row["serial"] for row in rows if row.get("serial")]

    if not serials:
        print("ERROR: No serials found in CSV.", file=sys.stderr)
        sys.exit(1)

    print(f"Claiming {len(serials)} device(s) into org inventory...")
    try:
        post(token, f"/organizations/{org_id}/inventory/claim", {"serials": serials})
        print(f"  ✓ Claimed: {', '.join(serials)}")
    except requests.HTTPError as e:
        print(f"  ✗ Claim failed: {e.response.text}", file=sys.stderr)
        sys.exit(1)


def do_add(token: str, rows: list[Row]) -> None:
    """Claim APs and add them to the network specified in each CSV row."""
    org_id: str = get_org_id(token)
    print("Fetching network list...")
    networks: dict[str, str] = get_networks(token, org_id)

    # Group devices by network
    by_network: dict[str, list[Row]] = {}
    for row in rows:
        net_name: str = row.get("network_name", "").strip()
        if not net_name:
            print(f"  WARN: Row for serial '{row['serial']}' has no network_name — skipping.")
            continue
        by_network.setdefault(net_name, []).append(row)

    for net_name, net_rows in by_network.items():
        net_id: str | None = networks.get(net_name)
        if not net_id:
            print(f"  ✗ Network not found: '{net_name}' — skipping {len(net_rows)} device(s).", file=sys.stderr)
            continue

        serials: list[str] = [r["serial"] for r in net_rows]
        print(f"\nAdding {len(serials)} device(s) to network '{net_name}'...")

        # Claim into org first
        try:
            post(token, f"/organizations/{org_id}/inventory/claim", {"serials": serials})
        except requests.HTTPError as e:
            print(f"  ✗ Org claim failed: {e.response.text}", file=sys.stderr)
            continue

        # Claim into network
        try:
            post(token, f"/networks/{net_id}/devices/claim", {"serials": serials})
            print(f"  ✓ Added to network: {', '.join(serials)}")
        except requests.HTTPError as e:
            print(f"  ✗ Network claim failed: {e.response.text}", file=sys.stderr)
            continue

        # Set name and tags per device
        for row in net_rows:
            serial: str = row["serial"]
            payload: Payload = {}
            if row.get("name"):
                payload["name"] = row["name"]
            if row.get("tags"):
                payload["tags"] = parse_tags(row["tags"])

            if not payload:
                continue

            try:
                time.sleep(RATE_LIMIT_DELAY)
                put(token, f"/devices/{serial}", payload)
                print(f"  ✓ Configured {serial}: name='{payload.get('name', '')}' tags={payload.get('tags', [])}")
            except requests.HTTPError as e:
                print(f"  ✗ Failed to configure {serial}: {e.response.text}", file=sys.stderr)


def do_update(token: str, rows: list[Row]) -> None:
    """Update name and/or tags on existing APs by serial."""
    print(f"Updating {len(rows)} device(s)...")

    for row in rows:
        serial: str = row.get("serial", "").strip()
        if not serial:
            print("  WARN: Row with empty serial — skipping.")
            continue

        payload: Payload = {}
        if row.get("name"):
            payload["name"] = row["name"]
        if row.get("tags"):
            payload["tags"] = parse_tags(row["tags"])

        if not payload:
            print(f"  WARN: No name or tags for {serial} — skipping.")
            continue

        try:
            time.sleep(RATE_LIMIT_DELAY)
            put(token, f"/devices/{serial}", payload)
            print(f"  ✓ Updated {serial}: name='{payload.get('name', '')}' tags={payload.get('tags', [])}")
        except requests.HTTPError as e:
            print(f"  ✗ Failed to update {serial}: {e.response.text}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meraki_ap_config.py",
        description=(
            "Batch configure Meraki APs via the Dashboard API.\n\n"
            "Modes (pick exactly one):\n"
            "  --claim   Claim APs into org inventory only\n"
            "  --add     Claim APs and add to the network specified in the CSV\n"
            "  --update  Update name/tags on already-claimed APs\n\n"
            "CSV columns:\n"
            "  serial        Required for all modes\n"
            "  name          Required for --add and --update\n"
            "  tags          Optional; semicolon-separated (e.g. floor-1;building-a)\n"
            "  network_name  Required for --add\n\n"
            "Examples:\n"
            "  python meraki_ap_config.py --claim  --source aps.csv --token YOUR_TOKEN\n"
            "  python meraki_ap_config.py --add    --source aps.csv --token YOUR_TOKEN\n"
            "  python meraki_ap_config.py --update --source aps.csv --token YOUR_TOKEN"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--claim",
        action="store_true",
        help="Claim APs into org inventory without adding to a network",
    )
    mode_group.add_argument(
        "--add",
        action="store_true",
        help="Claim APs and add them to the network specified in the CSV",
    )
    mode_group.add_argument(
        "--update",
        action="store_true",
        help="Update name and/or tags on already-claimed APs",
    )

    parser.add_argument(
        "--source",
        required=True,
        metavar="FILE",
        help="Path to the source CSV file",
    )
    parser.add_argument(
        "--token",
        required=True,
        metavar="TOKEN",
        help="Meraki Dashboard API token",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser: argparse.ArgumentParser = build_parser()
    args: argparse.Namespace = parser.parse_args()

    mode: str = "claim" if args.claim else "add" if args.add else "update"
    rows: list[Row] = load_csv(args.source, mode)

    print(f"Mode: --{mode} | Source: {args.source} | Rows: {len(rows)}\n")

    if mode == "claim":
        do_claim(args.token, rows)
    elif mode == "add":
        do_add(args.token, rows)
    else:
        do_update(args.token, rows)

    print("\nDone.")


if __name__ == "__main__":
    main()