# scripts/

One-off operational scripts that work against a running stack over HTTP (via
the API Gateway), rather than against any single service's code or database
directly. Each script is a plain, dependency-free Python file (stdlib only)
so it runs with any interpreter — no `uv sync` required.

## backfill_product_images.py

Adds a deterministic placeholder image (`picsum.photos/seed/{slug}/800/600`)
to every product that doesn't already have one. Logs in once as an admin —
admin bypasses product-service's seller-ownership check, so one token can
manage every seller's products. Safe to re-run: it skips any product that
already has at least one image, so a partial or repeated run doesn't create
duplicates.

```powershell
$env:GATEWAY_URL = "http://localhost:9000"
$env:ADMIN_EMAIL = "admin.integration@example.com"
$env:ADMIN_PASSWORD = "..."   # see tests/integration-tests/.env.integration
python scripts/backfill_product_images.py --dry-run   # preview first
python scripts/backfill_product_images.py             # then actually write
```

All three env vars are required — there's no hardcoded default credential,
intentionally, so this can't be run against the wrong environment by
accident.

Requires the gateway (and product-service behind it) to be reachable, and an
admin account to already exist — the integration-test seed data
(`tests/integration-tests/.env.integration.example`) has one for local dev.
