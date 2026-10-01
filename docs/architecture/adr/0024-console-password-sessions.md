# ADR-0024 — Console Password Authentication and Sessions

- **Status**: draft · pending maintainer review
- **Date**: 2026-10-02
- **Decides**: §0 ledger item 18 — propose role-based password authentication with persistent, revocable console sessions
- **回应 REQ**: REQ-S-4, REQ-F-14

## Context（背景）

- REQ-S-4 requires role-based authorization using a password or client certificate, authorization and audit for all control-console operations, and append-only audit logs.
- ADR-0016 assigns console authentication and complete audit to M4 but does not select an authentication or session mechanism.
- `services/console/access.py` currently implements pure role/permission policy and audit-record construction. `api.py` accepts injected identity and authorization callbacks. There is no account or session persistence.
- The console shares a PostgreSQL governance store. Its application uses a shared PostgreSQL connection that must remain dedicated and request-serialized; mutating `search_path` is not an acceptable isolation mechanism.
- M4b-5-2d2 is an engineering slice, not an authenticated service or acceptance evidence. Persistent audit integration remains undelivered.

## Decision（决策）

Propose role plus password authentication for the control console, subject to maintainer review. This is a design proposal, not an accepted decision or authorization to claim REQ-S-4 or M4b acceptance.

- Reuse the existing `VIEWER`, `OPERATOR`, `APPROVER`, and `ADMIN` roles, permissions, `MANAGE_USERS` permission, and two-person approval policy. Every control-console operation must authorize the actor and produce an audit event; durable append-only audit is a separate M4b-6b delivery gate.
- Store password verifiers as `pbkdf2-sha256$v1$<iterations>$32$<salt>$<digest>`, where salt and digest are canonical unpadded base64url encodings of the 16-byte cryptographically random salt and 32-byte derived key. The v1 parameters are PBKDF2-HMAC-SHA256 and 600,000 iterations. Password input is the exact UTF-8 encoding of the supplied string: do not normalize or truncate input; reject passwords exceeding 1,024 UTF-8 bytes before PBKDF2. Verify the digest with a constant-time comparison, using the algorithm, iteration count, key length, and salt recorded with each verifier. Require at least 12 characters. After successful login, rehash with the current parameters when they are stronger than those in the record. Never store or emit plaintext passwords in the database, logs, or audit records. No additional cryptography dependency is proposed.
- Issue an opaque 256-bit cryptographically random bearer session token. Store only its SHA-256 digest, user ID, CSRF-token digest, creation time, absolute expiry, and revocation metadata. Generate an unpredictable 256-bit CSRF value using a cryptographically secure random generator for each session; store only its SHA-256 digest, rotate it at login and on session renewal, and compare the submitted header value using a constant-time check. Sessions have an eight-hour absolute lifetime.
- On every authenticated request, resolve the active user and current roles from the database; never authorize from roles captured in a session. Password changes, role changes, and account disablement revoke all sessions belonging to that user atomically in the same database transaction as the corresponding mutation.
- Serialize password verification against account mutation by locking the account row for the login transaction and retaining that lock through successful session creation. Make verifier upgrades conditional on the exact verifier read; if the conditional update does not affect the account, do not return an authenticated principal.
- Set the session cookie as `__Host-as_console_session` and the CSRF cookie as `__Host-as_console_csrf`. Both cookies use `Secure`, `SameSite=Strict`, `Path=/`, and no `Domain`; the session cookie is `HttpOnly`, while the CSRF cookie is readable by browser code for the double-submit `X-CSRF-Token` header required on every state-changing request.
- Accept password login only over direct HTTPS or through an explicitly configured trusted proxy. A trusted proxy must strip client-supplied forwarded headers and set canonical HTTPS metadata. By default, the application trusts no forwarded headers; reject login over untrusted plain HTTP.
- Use the PostgreSQL governance store with schema-qualified, safe table names for users and sessions. Do not mutate `search_path`; preserve the dedicated, request-serialized shared-connection constraint. Do not use Redis for console sessions.
- Guard user management with `MANAGE_USERS`. Create the first administrator through a one-time CLI bootstrap that reads the password with `getpass`; provide neither a default password nor an unauthenticated claim endpoint. In one PostgreSQL transaction, the CLI locks the pre-existing singleton bootstrap row, checks atomically that no users or administrator exist, inserts the first `ADMIN`, and marks bootstrap complete. Ordinary user creation requires bootstrap completion under the same singleton-row lock. Repeated or concurrent bootstrap attempts fail. Subsequent role changes, password changes, and account disablement require administrator authorization and revoke that user's sessions in the same transaction as the change.
- Preserve the existing injected identity/authorization callback mode for tests and integrations. When session authentication is explicitly configured, it is the primary authentication path and fails closed; callback mode is not a fallback for failed session authentication. This design is not a feature toggle. Browser login UI remains M4b-7.
- Durable audit must persist the REQ-S-4 fields for authorized and denied attempts, and for reads and writes as appropriate: actor, timestamp, operation/action, resource, before value, and after value. Read operations may use null before/after values; write/change operations must carry canonical before/after JSON snapshots generated from allow-listed domain objects, never raw HTTP/body/free-form request data. Routes must redact secret values before append. The audit store also rejects sensitive key and credential-looking value patterns as defense-in-depth; this detection is not complete for arbitrary secrets and does not replace producer-side redaction.
- The audit store uses a dedicated non-`public` schema, owned by the migration/owner role; setup creates it when absent and rejects an existing schema with a different owner. The schema may contain only this store's events table, its owned event sequence, its `audit_event_id_pkey` index, the table's generated row and composite-array types, and its two guard functions. Reject unexpected existing relations, types, or routines before runtime grants, especially PUBLIC-executable or `SECURITY DEFINER` routines; do not preserve unreviewed user objects in this schema. Require the event sequence to be `bigint`, start and minimum `1`, increment by `1`, maximum `9223372036854775807`, and `NO CYCLE`; reject incompatible pre-existing settings before grants. The runtime API database role receives schema `USAGE` only, with no effective schema `CREATE` privilege, and must not own the schema, audit table, or sequence. Setup checks effective schema and sequence privileges, including inherited role grants; the runtime role may use/read the sequence but must not have effective sequence `UPDATE`. Never mutate `search_path`.
- The runtime API database role must have no effective `UPDATE`, `DELETE`, or `TRUNCATE` privileges on the audit table; these privileges must not merely be granted and rejected by triggers. The runtime role retains `INSERT` and `SELECT`. Use a separate migration/owner role and explicit database trigger/constraint defenses as defense-in-depth. Tests must verify effective grants and demonstrate denied attempts for each of `UPDATE`, `DELETE`, and `TRUNCATE`. M4b-6b remains a required gate before M4b acceptance until tests verify the persisted data fields and audit immutability.
- Split delivery: M4b-6a covers identity, password, and session integration. M4b-6b covers append-only persistent audit integration and remains required before M4b acceptance.

## Consequences（后果）

### Positive（正面）

- The proposal uses the existing authorization policy and approval separation while establishing a revocable server-side session boundary; each request sees current account status and roles, and account changes revoke sessions transactionally.
- Passwords and bearer tokens are not persisted in recoverable form; state-changing browser requests have a CSRF check.
- Bootstrap has an explicit out-of-band first-admin path and does not expose an unauthenticated account-claim surface.

### Negative / accepted（负面 / 已接受）

- This slice provides a local password-account lifecycle only. MFA, SSO, and client-certificate authentication are not included.
- Rate limiting depends on deployment ingress and remains a security follow-up; this proposal does not claim application-level rate limiting.
- HTTPS termination and trusted-proxy configuration remain deployment responsibilities and must be validated before production exposure.
- Persistent append-only audit is not delivered by the login/session design and remains the separate M4b-6b requirement.
- Password recovery, lockout policy, session listing, and other account lifecycle requirements are not selected here beyond the specified admin operations and password-change revocation.
- No REQ-S-4 or M4b acceptance is claimed. The proposal remains draft until maintainer review; integration and security verification are pending.

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| HTTP Basic credentials on every request | Repeatedly exposes reusable credentials to the request path and does not provide server-side session revocation or session lifecycle metadata. |
| Stateless signed session | Requires signing-key lifecycle and still lacks straightforward per-session revocation; the governance store is already the selected home for control-plane state. |
| mTLS-only console authentication | REQ-S-4 permits client certificates, but this would couple operator identity to certificate provisioning and does not satisfy the requested local password-account path. Certificate authentication remains outside this slice. |

## Evidence（证据）

- **Implementation evidence pending.** Existing evidence is limited to pure access policy, injected identity/authorization callbacks, and audit-record construction. No password verifier, user/session persistence, HTTP authentication integration, or durable append-only audit implementation is established by this ADR.
- This draft is design input only; it is not acceptance evidence.

## Related（相关）

- [ADR-0016 — In-boundary Security](0016-in-boundary-security.md)
- [ADR-0006 — Configuration Governance](0006-config-governance.md)
- [ADR-0007 — Data-Plane Split](0007-data-plane-split.md)
- [HLD](../hld.md), [LLD](../lld.md), and [implementation plan](../../plan.md)