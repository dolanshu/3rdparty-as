# Security policy

## Reporting

Report suspected vulnerabilities privately to the maintainer
(`dolan.d.shu@gmail.com`). Do not open a public issue for a security problem.
Include what you observed, how to reproduce it, and the version from `./VERSION`.

## Scope

In scope: the AS processes under `apps/` and `platform/`, the control plane under
`services/`, the deployment assets under `deploy/`, and the trunk-facing attack
surface.

Explicitly out of scope by design:

- **Lawful interception** — not implemented and not planned (ADR-0016).
- **Media handling** — the system is signalling-only (ADR-0004).
- **Charging and CDR** — not implemented (ADR-0017).

## What is expected of the system

- The SIP trunk is treated as **untrusted**: a peer is checked against the
  allowlist, and TLS terminates end to end with the S-SBC. Anyone able to
  impersonate the S-SBC can inject calls, so peer authenticity is not optional.
- Certificate rotation is a configuration hot update — no restart, no dropped
  in-flight call.
- Every console operation is authenticated and audited.
- Payload logging is switchable and off by default in logs.

## What is never committed

Keys, certificates, tokens, real network addresses and captures of real traffic.
Only `.env.example` placeholders belong in the repository.
