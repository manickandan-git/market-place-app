# Marketplace User Service

## 1. Purpose and ownership

The User Service is the authoritative store for marketplace profile, address,
preference, privacy-request, and seller-profile data.

| Capability | Authoritative owner |
|---|---|
| Credentials, password recovery, email verification | Identity Service |
| JWT access/refresh tokens and sessions | Identity Service |
| Roles and role assignment (`buyer`, `seller`, `admin`) | Identity Service |
| Immutable authenticated `user_id` | Identity Service |
| Buyer and seller profiles | User Service |
| Addresses and defaults | User Service |
| Language, time zone, notification and marketplace preferences | User Service |
| Profile-image reference | User Service |
| Profile deactivation/deletion workflow | User Service, coordinated with Identity |

The User Service never stores passwords, issues tokens, or changes roles. It
validates Identity-issued JWTs and uses the immutable `sub` claim as `user_id`.

## 2. functional scope

### Profiles

- Create a local profile on first authenticated access or from an
  `identity.user.registered.v1` event.
- Retrieve the authenticated user's combined profile.
- Partially update mutable profile fields.
- Maintain buyer fields: display name, legal name, phone reference, locale,
  profile-image reference, and optional date of birth.
- Maintain seller fields only for users with the `seller` role: store name,
  public description, support contact reference, business type, and seller
  status.
- An authenticated owner may read and update their private profile.
- Public seller-profile retrieval exposes an explicit allowlist only.
- Admin/support access requires an Identity-issued role/scope and is audited.

### Addresses

- Create, list, retrieve, partially update, and delete addresses owned by the
  authenticated user.
- Address types are `shipping` and `billing`; one physical address may be
  represented separately for each type.
- At most one default address exists per user and address type.
- Making an address default atomically clears the previous default of the same
  type.
- Deleting the current default either promotes a replacement supplied by the
  request or leaves the type without a default; it never silently chooses one.
- Validate required lines, city/locality, country code (ISO 3166-1 alpha-2),
  postal code length, field lengths, and normalization. Country-specific
  postal validation can be extended later.
- Address mutations use optimistic concurrency through a numeric `version` and
  `If-Match` header. Stale writes return `412 Precondition Failed`.

### Preferences

- Partially update language (BCP 47 tag), IANA time zone, currency (ISO 4217),
  marketplace preferences, and notification channel/topic preferences.
- Notification preferences express consent only; the Notification Service owns
  templates, providers, delivery attempts, and delivery status.
- Store only a profile-image object reference/URL; binary upload and media
  processing belong to a future Media Service.

### Lifecycle, privacy, and reliability

- Support profile deactivation and reactivation policy enforcement.
- Accept access/export and deletion requests with status tracking.
- Deletion is asynchronous: immediately restrict processing, retain legally
  required records, publish a request event, and later anonymize/delete
  eligible profile data.
- Emit audit events for sensitive reads, all mutations, role-based overrides,
  privacy requests, and lifecycle changes.
- Mutation endpoints accept `Idempotency-Key`. The service stores the user,
  operation, request hash, response, and expiry. Reuse with a different payload
  returns `409 Conflict`.
- Profile and seller mutations use optimistic concurrency with `version` and
  `If-Match`; responses expose `ETag`.

## 3. Authorization model

JWT validation verifies signature, issuer, audience, expiry, and allowed
algorithm. The service derives:

- `user_id` from immutable `sub`;
- roles from `roles`;
- fine-grained permissions from `scope`/`scp` where present.

Rules:

- Buyers manage only their own profile, preferences, and addresses.
- Seller-profile endpoints require the `seller` role.
- Admin/support cross-user operations require explicit scopes such as
  `users:read:any` or `users:write:any`; a role name alone is insufficient for
  elevated mutation.
- Request body/path values never override the authenticated owner.
- Deactivated users receive only lifecycle/privacy access permitted by policy.

## 4. Domain and PostgreSQL model

| Aggregate/table | Key data and constraints |
|---|---|
| `user_profiles` | `user_id` PK/FK-by-contract, names, birth date, phone reference, image reference, status, `version`, timestamps |
| `seller_profiles` | `user_id` PK, store name, slug unique, description, support contact reference, business type, status, `version`, timestamps |
| `addresses` | UUID PK, `user_id`, type, recipient, address fields, country, phone reference, `is_default`, `version`, timestamps, soft-delete timestamp |
| `user_preferences` | `user_id` PK, language, time zone, currency, JSONB marketplace preferences, `version`, timestamps |
| `notification_preferences` | UUID PK, `user_id`, channel, topic, enabled, consent timestamp, unique `(user_id, channel, topic)` |
| `privacy_requests` | UUID PK, `user_id`, type, status, requested/completed timestamps, result reference |
| `idempotency_records` | `(user_id, operation, key)` unique, request hash, status code, response JSONB, expiry |
| `audit_events` | UUID PK, actor/subject IDs, action, resource, request/correlation IDs, metadata JSONB, timestamp |
| `outbox_events` | UUID PK, aggregate identity, event type/version, payload JSONB, occurrence/publication timestamps, retry data |

Important database invariants:

- UUID identifiers and UTC timestamps.
- Partial unique index on `(user_id, address_type)` where
  `is_default = true AND deleted_at IS NULL`.
- Check constraints for enum-like statuses and non-negative versions.
- Transactional outbox rows are committed in the same transaction as domain
  changes.
- User Service does not use a database foreign key to the Identity database;
  `user_id` is an immutable cross-service contract.

## 5. REST API contract

Base path: `/api/v1`

| Method and path | Purpose |
|---|---|
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database/dependency readiness |
| `GET /me` | Retrieve authenticated combined profile |
| `PATCH /me` | Partial buyer/common profile update |
| `GET /me/seller` | Retrieve own seller profile |
| `PUT /me/seller` | Create seller profile; seller role required |
| `PATCH /me/seller` | Partial seller profile update |
| `GET /sellers/{seller_id}` | Retrieve allowlisted public seller profile |
| `GET /me/addresses` | List owned addresses, filterable by type |
| `POST /me/addresses` | Create address |
| `GET /me/addresses/{address_id}` | Retrieve owned address |
| `PATCH /me/addresses/{address_id}` | Partial address update |
| `DELETE /me/addresses/{address_id}` | Delete owned address |
| `GET /me/preferences` | Retrieve preferences |
| `PATCH /me/preferences` | Partial preference update |
| `GET /me/notification-preferences` | Retrieve notification consent |
| `PUT /me/notification-preferences` | Replace/upsert channel-topic choices |
| `POST /me/deactivation` | Deactivate own profile |
| `POST /me/reactivation` | Request/perform permitted reactivation |
| `POST /me/privacy-requests` | Create export/access/deletion request |
| `GET /me/privacy-requests/{request_id}` | Retrieve owned request status |

Mutation conventions:

- `Authorization: Bearer <Identity JWT>` is required.
- `If-Match: "<version>"` is required for updates/deletes of existing
  versioned resources.
- `Idempotency-Key` is required for creates and lifecycle/privacy operations.
- `X-Correlation-ID` is accepted or generated and returned.
- Errors use RFC 9457 Problem Details.
- Collection pagination uses opaque cursors.

## 6. Domain and integration events

Consumed initially:

- `identity.user.registered.v1`
- `identity.user.roles_changed.v1`
- `identity.user.deactivated.v1`
- `identity.user.deleted.v1`

Published through the transactional outbox:

- `user.profile.created.v1`
- `user.profile.updated.v1`
- `user.address.created.v1`
- `user.address.updated.v1`
- `user.address.deleted.v1`
- `user.preferences.updated.v1`
- `user.seller_profile.updated.v1`
- `user.profile.deactivated.v1`
- `user.profile.reactivated.v1`
- `user.privacy_requested.v1`
- `user.deletion_completed.v1`

Events contain identifiers and the minimum changed data; they do not contain
credentials, tokens, complete addresses, or unnecessary personal data.

## 7. Protocol decision

| Criterion | REST/OpenAPI | gRPC | GraphQL |
|---|---:|---:|---:|
| Browser/client compatibility | Excellent | Limited without gateway | Excellent |
| CRUD/resource semantics | Excellent | Good | Good |
| Contract/tooling | Excellent | Excellent with protobuf | Good with schema |
| Internal latency/throughput | Good | Excellent | Good |
| Caching/HTTP observability | Excellent | Good | More complex |
| Frontend aggregation | Fair | Poor | Excellent |
| MVP operational cost | Low | Medium | Medium/high |
| Fit as authoritative User API | **Best** | Conditional | Not preferred |

Decision: REST/OpenAPI is the authoritative contract. Introduce gRPC
only after measurements show a latency-sensitive or high-volume internal call,
using versioned protobuf contracts and REST compatibility where required.
GraphQL belongs in a future BFF/API aggregation layer for frontend composition.
The MVP will not operate all three protocols.

## 8. Non-functional requirements

- PostgreSQL is the service-owned database; no cross-service table access.
- SQLAlchemy 2.x async sessions and Alembic migrations.
- FastAPI with generated OpenAPI, strict Pydantic validation, and Problem
  Details errors.
- Atomic transactions for aggregate update, audit record, idempotency result,
  and outbox event.
- Target p95 under 250 ms for single-resource reads and under 400 ms for writes
  in the local baseline, excluding external dependencies.
- Structured logs with request/correlation/user identifiers; never log tokens
  or sensitive address content.
- OpenTelemetry-ready metrics/traces; health endpoints; database pool metrics.
- TLS at deployment boundaries, encrypted storage/backups, least-privilege DB
  role, configurable retention, and redaction.
- Backward-compatible `/api/v1` evolution and additive event changes within a
  major event version.
- Local development and Docker Compose first. Kubernetes is explicitly
  postponed.

## 9. Acceptance criteria

1. Identity-issued valid JWTs authorize requests by `sub`; invalid issuer,
   audience, signature, or expiry returns `401`.
2. One user cannot read or mutate another user's private resources.
3. Buyer APIs work for buyers; seller mutations fail with `403` without the
   seller role.
4. Profile, seller, address, and preference partial updates preserve omitted
   fields.
5. Concurrent writes with a stale `If-Match` return `412` and do not change
   state.
6. Concurrent attempts to set two defaults leave exactly one default for each
   user/address type.
7. Duplicate idempotent creates return the original result; mismatched reuse
   returns `409`.
8. Deactivation and privacy requests are authorized, auditable, and emit
   outbox events without synchronously deleting required data.
9. Every mutation writes an audit record and appropriate outbox event in the
   same database transaction.
10. Alembic upgrades a clean PostgreSQL database and downgrades in the
    tests.
11. Unit, API integration, authorization, validation, idempotency, and
    concurrency tests pass locally and in Docker Compose.
12. Identity and Notification integration tests pass without either service
    sharing User Service tables.

## 10. Incremental implementation sequence

1. Project metadata, settings, minimal FastAPI app, and health tests.
2. Async database engine/session, declarative base, and readiness check.
3. SQLAlchemy domain models and enums.
4. Initial Alembic migration with constraints and indexes.
5. Pydantic request/response schemas and Problem Details.
6. Identity JWT validation and authenticated principal dependency.
7. Profile and seller repositories/services/routes.
8. Address invariants, CRUD, idempotency, and concurrency.
9. Preferences and notification-preference APIs.
10. Audit and transactional outbox.
11. Deactivation/privacy workflow and events.
12. Full test suite, Dockerfile, and Compose integration.

## 11. Known gaps )

- **No privacy-request cancellation endpoint.** `POST /me/privacy-requests`
  and `GET /me/privacy-requests/{request_id}` exist, but there is no way to
  transition a request out of `pending`/`in_progress` (`PrivacyRequestStatus`
  defines `CANCELLED`, but nothing in the API can set it). This is a dead end
  in practice: `reactivate()` refuses while the profile is
  `deletion_pending`, and `uq_active_privacy_request_per_type` blocks
  submitting another request of the same type while one is active — so a
  buyer who requests deletion cannot reactivate, re-request, or cancel.
  Implementing this requires deciding (a) the endpoint shape (e.g. `POST
  /me/privacy-requests/{request_id}/cancel`), (b) whether cancelling a
  deletion request reverts the buyer profile back to `active`, and (c)
  setting `resolved_at` to satisfy
  `ck_privacy_requests_resolution_timestamp_matches_status`, which requires a
  non-null `resolved_at` whenever status is `completed`/`rejected`/
  `cancelled`.

