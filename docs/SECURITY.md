# Security

Security & privacy outrank submission speed. See THREAT_MODEL.md and PRIVACY.md.

## Identity & access
Secure auth (Argon2 password hashing), server-side sessions, CSRF protection on
mutating requests, rate limiting, brute-force lockout/backoff, optional MFA
(TOTP), least privilege, admin/maintenance surface isolated from normal use.

## Data protection
Treat resume, name, email, phone, address, work authorization, transcripts,
application answers, recruiting email, and offer docs as **sensitive**.
- TLS in transit; encryption at rest (DB + object storage).
- Private object storage only; access via short-lived **signed URLs**.
- Log redaction of PII; secrets only in a secret manager / env, never committed.
- No full PII in ordinary logs; no full sensitive data in LLM request logs.
- Regular backups; user data export; hard delete; revoke third-party connections.

## LLM security
- JD/web content is untrusted; it can never override system rules, exfiltrate PII,
  or invoke tools.
- Tool calling uses a strict allowlist; all LLM outputs pass schema validation.
- Minimize sensitive fields sent; record each call's purpose and data scope.
- Support disabling cloud models and using a local model.

## Browser extension
Least privilege host permissions, reads only the active application page the user
opened, never stores account credentials, never bypasses site controls, never
background-submits, never uploads full pages to third parties, always shows what
it is filling, audit-logs sensitive actions.

## Audit
Append-only `audit_logs`: who changed personal info, who generated answers, which
model, which sources, what was auto-filled, what the user confirmed, when
submitted, and external responses. Not editable by ordinary operations.
