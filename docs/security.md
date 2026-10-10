# Security configuration and review

## Authentication

`APP_ENV` defaults to `production`. Configure complete Google sign-in settings under `[auth]` and
`[auth.google]` in Streamlit Secrets. Missing, unreadable, incomplete or placeholder authentication settings
stop the UI before it opens shared research storage. Logged-in sessions must have a provider subject ID.

For private development only, set `APP_ENV=local` in your local `.env`. This explicitly enables the shared
local administrator when sign-in is unavailable. Never deploy that `.env` or use local mode on a public server.
Use `.streamlit/secrets.toml.example` for deployment configuration; keep real secrets untracked.

## Evidence handling

Planning input, extracted passages, contradiction quotes, insight/Q&A matrices and report drafts are wrapped
as untrusted data before LLM processing. Source IDs are HTML-escaped, and injected boundary tags are removed
case-insensitively. Structured outputs remain schema-validated. Contradiction verdicts use a fixed enum;
insights containing unknown claim IDs are rejected; report rewrites that remove or change citation markers
fall back to the deterministic report. These measures do not prove factual correctness or eliminate prompt injection.

Regression tests cover missing/partial/unreadable auth, missing identity, production guest behavior, boundary
escape attempts, invalid verdicts, untrusted evidence in downstream prompts and citation-marker tampering.
They use fake models and offline data, not live-model attack evaluations.

## Credential checks

Run `python scripts/scan_secrets.py` from this repository. It scans tracked and non-ignored new working files,
plus all commits reachable from local Git references, checking known provider-key formats, private keys,
credential URLs and common credential assignments. Only candidate type, path, line and commit are printed;
matched values are withheld. A candidate causes a nonzero exit for integration into future CI.

The initial scan on 11 October 2026 found no candidates in 77 tracked working paths and 145 unique blobs
across eight reachable commits. Ignored private secret files were not opened by the scan. This is a pattern
scan, not proof that no secrets exist: unknown formats, inaccessible remote references, deleted references,
Git LFS payloads and external logs are outside its coverage. Nothing was sent to a credential-validation service.

If a genuine exposed credential is found, revoke/rotate it at its provider and update deployment secrets.
Removing it from the current source alone does not invalidate a credential or remove historical exposure.
No credentials were rotated during this change because no exposure candidate was found.

## Scope

This change does not add per-user quotas or global concurrency limits. Live OAuth, deployed application
behavior and live-model injection resistance still require deployment verification.

## Configurable LangSmith observability

Tracing exports telemetry to the configured LangSmith region. Custom request spans omit arguments and content bodies, but retain model identifiers, attempt numbers, safe request metrics and opaque research IDs. Graph input/output hiding defaults to true; explicit environment settings can override it. Hiding payloads does not sanitize metadata or pre-existing graph error strings. Inspect error and metadata paths before tracing private workloads.

Keep real LangSmith keys in ignored local configuration or deployed Secrets. Never use a shortened portal key, print credentials during diagnostics or commit them. `LANGSMITH_TRACING=false` is the research tracing master switch; its runtime off behavior still needs verification. No per-user quotas or global concurrency limits were introduced.

See [observability.md](observability.md) for the complete privacy scope, troubleshooting and evidence-based verification record.

## Authentication console diagnostics

Temporarily set top-level `AUTH_DIAGNOSTICS = "true"` in deployed Streamlit Secrets (before `[auth]`), then reboot. Locally use `AUTH_DIAGNOSTICS=true` in `.env`. Inspect the deployment's server logs, not the browser console. Restore false after diagnosis.

- `AUTH_CONFIG`: required authentication field names with true/false status; secret-loading exception class; callback HTTPS, path and local-host checks. Logged once per session/configuration status change. True means a nonempty string passed the existing placeholder check, not that Google accepted the credential.
- `AUTH_BLOCKED`: production stopped because authentication configuration was missing, incomplete or unreadable. This occurs before Google login; changing Google's allowed URLs alone cannot fix missing deployed Secrets.
- `AUTH_LOGIN_START`: the app attempted to start Google sign-in.
- `AUTH_LOGIN_FAILED`: synchronous login-start failure, with exception class only.
- `AUTH_SESSION_ACCEPTED`: a signed-in session with a provider subject reached the app; no identity values are logged.
- `AUTH_SESSION_INVALID`: the returned session has no usable provider subject.

Both localhost and production redirect URIs may be registered in Google Cloud. The deployed `[auth].redirect_uri` must select the exact production HTTPS callback ending in `/oauth2callback`; local configuration selects localhost. Diagnostics do not remotely inspect Google's registered redirect URIs, test credentials, or intercept callback errors handled internally by Streamlit/Authlib. Do not enable HTTP wire logging or share complete secret files to diagnose those errors.
