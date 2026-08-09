#!/usr/bin/env python3
"""Backfill a placeholder image for every product that has none.

Logs in once as an admin (admin role bypasses the seller-ownership check in
product-service, so one token can manage every seller's products), pages
through every product via GET /api/v1/seller/products, and for any product
whose detail view has an empty `images` list, adds one seeded placeholder
image (https://picsum.photos/seed/{slug}/800/600 - deterministic per
product, so re-running is a no-op for products that already got one).

Usage:
    GATEWAY_URL=http://localhost:9000 \
    ADMIN_EMAIL=admin.integration@example.com \
    ADMIN_PASSWORD=... \
    python scripts/backfill_product_images.py [--dry-run]

Env vars:
    GATEWAY_URL     required. No default, so this can't accidentally be
                    pointed at production without noticing.
    ADMIN_EMAIL     required. See tests/integration-tests/.env.integration
                    for the local dev seed value.
    ADMIN_PASSWORD  required, same as above. Never hardcode this - it's a
                    live credential and this file is checked into git.

Flags:
    --dry-run       list what would be added without writing anything.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required env var: {name}")
    return value


GATEWAY_URL = require_env("GATEWAY_URL")
ADMIN_EMAIL = require_env("ADMIN_EMAIL")
ADMIN_PASSWORD = require_env("ADMIN_PASSWORD")
PAGE_SIZE = 100


def request(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = f"{GATEWAY_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def login() -> str:
    resp = request(
        "POST",
        "/api/v1/auth/login",
        body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    return resp["access_token"]


def list_all_products(token: str) -> list[dict]:
    products = []
    page = 1
    while True:
        resp = request(
            "GET",
            f"/api/v1/seller/products?page={page}&page_size={PAGE_SIZE}",
            token=token,
        )
        products.extend(resp["items"])
        if page >= resp["pagination"]["total_pages"]:
            break
        page += 1
    return products


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be added without writing anything",
    )
    args = parser.parse_args()

    token = login()
    products = list_all_products(token)
    print(f"Found {len(products)} product(s) total.")
    if args.dry_run:
        print("(dry run - no images will be created)\n")

    added, skipped, failed = 0, 0, 0
    for summary in products:
        product_id = summary["id"]
        slug = summary["slug"]
        detail = request("GET", f"/api/v1/seller/products/{product_id}", token=token)
        if detail["images"]:
            skipped += 1
            continue

        image_url = f"https://picsum.photos/seed/{slug}/800/600"
        if args.dry_run:
            added += 1
            print(f"  would add: {slug} -> {image_url}")
            continue

        try:
            request(
                "POST",
                f"/api/v1/seller/products/{product_id}/images",
                token=token,
                body={"url": image_url, "alt_text": summary["name"], "sort_order": 0},
            )
            added += 1
            print(f"  + {slug} -> {image_url}")
        except RuntimeError as exc:
            failed += 1
            print(f"  ! {slug} failed: {exc}", file=sys.stderr)

    verb = "would add" if args.dry_run else "added"
    print(f"\nDone. {verb}={added} skipped(already had image)={skipped} failed={failed}")


if __name__ == "__main__":
    main()
