# Deployment and verification

## Configuration

Deploy this repository with `app.py` as the Streamlit entry point, using the dependency versions in `constraints.txt`. Set `APP_ENV="production"` in the deployment's Secrets. Configure `[auth]` with the public `redirect_uri` ending in `/oauth2callback` and a strong random `cookie_secret`, and `[auth.google]` with the Google client ID, client secret and discovery URL from `.streamlit/secrets.toml.example`. Register exactly the same HTTPS callback with the identity provider. Never commit actual secrets or deploy a developer `.env`.

Configure `ADMIN_EMAILS` only for trusted operators. Set provider keys for the live capabilities you intend to demonstrate. If using shared persistent storage, configure both `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`; otherwise the app uses SQLite at `APP_DB_PATH` and the host may discard that file on restart. `APP_ENV` controls authentication policy, not database selection. Missing production authentication stops the app before shared storage is opened.

For cost estimates, configure `LLM_INPUT_USD_PER_MILLION` and `LLM_OUTPUT_USD_PER_MILLION` for the active model. Update rates whenever the model changes. No user quotas or global concurrency controls are provided.

## Public availability check

```bash
python scripts/check_deployment.py https://YOUR-APP.streamlit.app
```

This checks the public app response and Streamlit health endpoint. A healthy HTTP server does not prove that login, providers, persistence or charts work. The command deliberately does not accept credentials or query strings.

## Hosted workflow checklist

Record date, deployed revision, model, source providers, outcome and any error for each step. Avoid personal data and secret values in screenshots or logs.

- Open the URL in a fresh browser: verify welcome screen, guest demo restrictions and a completed synthetic demo.
- Sign in using a designated test account; verify callback, logout and sign-in again.
- Run live research with an actual search provider; inspect sources, passage quotations, claim types and citations.
- Upload a CSV with real sourced numeric rows and units. Include that document in a live investigation; verify the Charts tab values, source passages and CSV download against the original file.
- Try a document with incompatible units or missing values: inspect extraction notes; verify no invented values appear.
- Open every results tab and progress/history/settings screen; check desktop and narrow/mobile layouts.
- Export Markdown, HTML and PDF; verify citations and numeric evidence are preserved. Graph images are not embedded in these exports.
- Ask a follow-up question; verify citations refer to the retrieved evidence.
- Compare the budget display with provider usage. Include a retry/failure scenario in a controlled test environment; distinguish observed usage from unreported allowance and partial cost estimates.
- Use a second test account: ensure the first account's runs/documents cannot be listed, opened, exported or deleted.
- Restart/redeploy and reopen the test run; verify persistent storage retains charts and history.
- Exercise missing authentication in a separate test deployment: verify it stops before database access.

## Verification status

The upgrade has offline automated tests for the graph, ingestion, chart provenance, claim integrity, budgets, persistence, owner isolation, exports and Streamlit screens. **The public deployment workflow has not yet been verified.** Local screenshots confirm live model/provider traces, but do not establish the complete hosted workflow. They require a supplied public URL, configured credentials and test-account access. Fill in the hosted checklist after execution; do not describe offline tests or a health check as a deployed end-to-end pass.

## Configurable LangSmith observability

Configure top-level `LANGSMITH_TRACING`, `APP_API_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` and the workspace-region endpoint in Streamlit Secrets before TOML table headers. Keep `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` enabled for private data. Use a separate production tracing project, and supply a workspace ID if the key requires it. Restart after configuration changes.

See [observability.md](observability.md) for an APAC example, portal/token instructions and 403 troubleshooting. Local traces were confirmed by screenshots; deployed tracing, master-off, graph-only and telemetry-failure behavior remain unverified. Complete those checks alongside the hosted workflow checklist above.

## Authentication console diagnostics

Temporarily set top-level `AUTH_DIAGNOSTICS = "true"` in deployed Streamlit Secrets (before `[auth]`), then reboot. Locally use `AUTH_DIAGNOSTICS=true` in `.env`. Inspect the deployment's server logs, not the browser console. Restore false after diagnosis.

- `AUTH_CONFIG`: required authentication field names with true/false status; secret-loading exception class; callback HTTPS, path and local-host checks. Logged once per session/configuration status change. True means a nonempty string passed the existing placeholder check, not that Google accepted the credential.
- `AUTH_BLOCKED`: production stopped because authentication configuration was missing, incomplete or unreadable. This occurs before Google login; changing Google's allowed URLs alone cannot fix missing deployed Secrets.
- `AUTH_LOGIN_START`: the app attempted to start Google sign-in.
- `AUTH_LOGIN_FAILED`: synchronous login-start failure, with exception class only.
- `AUTH_SESSION_ACCEPTED`: a signed-in session with a provider subject reached the app; no identity values are logged.
- `AUTH_SESSION_INVALID`: the returned session has no usable provider subject.

Both localhost and production redirect URIs may be registered in Google Cloud. The deployed `[auth].redirect_uri` must select the exact production HTTPS callback ending in `/oauth2callback`; local configuration selects localhost. Diagnostics do not remotely inspect Google's registered redirect URIs, test credentials, or intercept callback errors handled internally by Streamlit/Authlib. Do not enable HTTP wire logging or share complete secret files to diagnose those errors.
