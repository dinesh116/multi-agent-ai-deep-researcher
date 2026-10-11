# 🔬 Deep Researcher AI

A multi-agent research assistant for complex, multi-hop questions. It plans an investigation, searches web,
academic and uploaded sources, evaluates credibility, extracts claims linked to exact passages, detects
contradictions, runs bounded follow-up research on gaps, generates clearly labelled insights and hypotheses,
and compiles a cited report you can export, reopen and question.

Built with **LangGraph** (orchestration), **Streamlit** (dashboard), **OpenRouter** via the OpenAI SDK (optional
LLM), **OpenAlex / Crossref / arXiv / Tavily** (sources), **SQLite**, **PyMuPDF**, **Trafilatura** and **Plotly**.

> Demo mode uses a **synthetic, fictional** corpus and is labelled as such everywhere. A citation that passes
> validation is *traceable*, which is not the same as *true*. Always check important conclusions against the
> original sources.

---

## Quick start

Requires Python 3.12+ (developed on 3.13). From this folder:

```bash
uv venv --python 3.13                 # or: python3.13 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt -c constraints.txt    # or: pip install -r requirements.txt -c constraints.txt

cp .env.example .env                  # optional: add keys for live research (see below)
streamlit run app.py                  # http://localhost:8501
pytest                                # offline; no API keys needed
```

**From VS Code:** open this folder, select the `.venv` interpreter, then use **Run and Debug → "Deep Researcher AI
(Streamlit)"**. Tests appear in the Testing panel.

## Deployment security

`APP_ENV` defaults to `production`: sign-in (`[auth]` plus at least one provider) must be fully configured or the app stops before opening
its shared repository. For private local development without accounts, explicitly set `APP_ENV=local`
(the `.env.example` does this). Never use local mode for a public deployment. Set `APP_ENV="production"`
in deployed Streamlit Secrets; do not deploy your local `.env`.

Run `python scripts/scan_secrets.py` to scan tracked and non-ignored new files plus reachable Git history.
The scanner reports candidate locations only, never credential values. See [docs/security.md](docs/security.md).

Source passages, evidence matrices and report drafts are treated as untrusted data at LLM boundaries.
Schema validation, allowed evidence IDs and preservation of report citation markers provide additional checks;
these controls reduce prompt-injection risk but do not guarantee factual accuracy or complete prevention.

## Accounts, privacy and storage

**Accounts (required for public deployment).** With sign-in configured (Google, Microsoft and/or email), every research run, uploaded document, follow-up Q&A and
activity entry belongs to the signed-in user, and every database query is filtered by that user. Users can't list,
open, delete or export each other's data, even by guessing a run id. Visitors who aren't signed in are **guests**:
they can run the synthetic demo (three preselected questions), which is visible only in their browser session and
deleted after 24 hours, but not live research, uploads or settings. **Research library → My activity** shows sign-ins, runs, Q&A, exports and uploads,
and **Delete my data** removes everything a user owns. Admins (`ADMIN_EMAILS`) manage models and providers and see
usage counts per user, never content; admin rights also require the provider to report the email as verified.
Without sign-in configured, only explicit `APP_ENV=local` allows a single local administrator. Production stops.

**Sign-in options.** The Sign in page shows one button per provider configured in Secrets (see
`.streamlit/secrets.toml.example`): **Google**, **Microsoft** and **email**. "Email" is a hosted OpenID Connect
service with email sign-up, verification and password reset (for example Auth0), so **Create account** works without
the app ever handling passwords. An account is created the first time someone signs in. Identities are tied to the
issuer that signed them (Google ids unchanged; other providers prefixed), and an unknown issuer is rejected.

**Profiles.** **Update profile** stores optional details (display name, age range, sex, education, industry, role,
research interests) for the signed-in user only. They are never shown to admins or sent to providers or the LLM, and
**Delete my data** removes them together with the account record.

**Set up Google sign-in (about 10 minutes; Microsoft and email providers are configured the same way):**
1. Google Cloud Console → *APIs & Services* → *OAuth consent screen*: create one (External, your email as a test user).
2. *Credentials* → *Create credentials* → *OAuth client ID* → *Web application*. Add authorised redirect URIs
   `http://localhost:8501/oauth2callback` and `https://<your-app>.streamlit.app/oauth2callback`.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (git-ignored) and fill in `[auth]` and
   `[auth.google]`. For the deployed app, paste the same content into Streamlit Cloud → *Settings* → *Secrets*, with the
   deployed `redirect_uri`.

**Persistent storage (optional): Turso.** By default data is stored in a local SQLite file, which on Streamlit Cloud
is wiped on every restart. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (in `.env` or Secrets) to store
everything in a hosted Turso database instead. The app keeps an embedded replica (fast local reads), and writes go to
Turso, so history survives restarts and redeploys. Create a token with `turso db tokens create <db>` or in the Turso
dashboard. Existing single-user databases are migrated automatically (their data becomes the local user's).

## Demo mode vs live research

| | Demo mode (default) | Live research |
|---|---|---|
| Sources | 27 bundled **synthetic** sources (`data/sample_research/corpus.json`) | OpenAlex, Crossref, arXiv (no key), Tavily web/news (`TAVILY_API_KEY`), your uploads |
| Network | none | search APIs + bounded fetching of public result pages |
| Agents | deterministic | deterministic, plus LLM planning, extraction, adjudication, insights and prose when `OPENROUTER_API_KEY` is set |
| Labels | every source, reference and export says SYNTHETIC | live / cached / uploaded origin shown per source |

The demo corpus only covers AI and enterprise software, so **demo mode is limited to three preselected questions**
(`DEMO_QUESTIONS` in `src/models/research.py`), for guests and signed-in users alike; the research service rejects
any other demo question, because it would retrieve unrelated sources and produce a misleading report:

1. *How will agentic AI transform enterprise software over the next five years?*
2. *Which emerging technologies could create new business opportunities in India?*
3. *What evidence supports or contradicts the claim that AI agents will replace traditional SaaS workflows?*

The corpus deliberately includes contradictions (e.g. 38% vs 72% agent adoption), a vendor press release reprinted by
a news site, an outdated 2019 forecast, opinion pieces, conflict-of-interest material and a prompt-injection attempt,
so every analysis feature has something to find. Live research (signed in) accepts any question.

## Configuration

Edit `.env` (never committed):

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Enables LLM features. Without it, agents run deterministically. |
| `OPENROUTER_MODEL` | Default `openai/gpt-4o-mini`; any OpenRouter model with JSON output. Can be overridden on the Settings page. |
| `OPENROUTER_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `TAVILY_API_KEY` | Enables live web and news search (<https://tavily.com>) |
| `CONTACT_EMAIL` | Sent to OpenAlex/Crossref for polite API use (recommended) |
| `APP_DB_PATH`, `HTTP_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`, `MAX_UPLOAD_MB` | Optional |

OpenRouter only handles language tasks. It is **not** used for web search; source discovery is done by the search
providers, which you can toggle on the **Settings** page. Without Tavily, live mode still searches the academic
sources and your uploads, and says so in the run log.

## The pages

The interface is a frosted-glass design with high-contrast **dark and light themes** (Sora headings, DM Sans body,
cyan and violet accents). The app follows the device setting; switch in the menu (⋮ → Settings → Theme). Layouts
adapt to desktop, tablet and phone, and animations stop for visitors who prefer reduced motion. The Deep Research Agent
robot is the logo; the lab scene appears on the home pages. The left panel holds the menu, **New research**, runs
**In progress**, recent research and the profile block.

1. **Home**: visitors see a minimal introduction with **Try Demo** or **Sign in**. Signed-in users get their research
   home: a question box that starts a run directly, **Get to know your Agents team** (animated tiles for the eight
   agents), **How an investigation flows** (the LangGraph workflow, showing the parallel steps and the bounded
   follow-up loop) and recent investigations.
   - **Sign in**: Sign in / Create account with the configured providers, or try the demo without an account.
   - **Update profile**: optional personal and research-interest details (signed-in users).
2. **Research workspace**: Live/Demo switch (guests: demo only); demo shows the three question cards, live shows a
   free-text question with suggestions; depth cards (Quick/Standard/Deep); advanced settings (context, objectives,
   follow-up rounds, source types, dates, LLM, documents); recent investigations.
3. **Agents in action**: live agent list with status, activity timeline and progress bar while a run is queued or
   executing, with **Stop & write report**; for a past run, the per-agent audit trail, budget usage, stopping
   decision, full event log and search activity. Research runs in a background job runner, so you can leave the page,
   refresh or switch devices and reattach from **In progress** in the sidebar.
4. **Research results**: one investigation in tabs: *Overview* (executive summary, key findings, at a glance),
   *Evidence* (filterable sources, assessments, passages, claims), *Analysis* (evidence matrix, contradictions,
   agreement vs uncertainty, gaps, coverage), *Insights* (observed / inferred / speculative), *Charts* (extracted values and provenance), *Full report* (cited
   report + citation traceability) and *Ask* (follow-up Q&A). Export (Markdown/HTML/PDF) and Refine in the header.
5. **Research library**: search, sort and status filters; open or delete runs; *My activity*; *Delete my data*.
6. **Settings**: capabilities, personal defaults and documents; admin-only models, providers, cache and usage.

## How it works (summary)

```
START → Planner → Retriever → Source Evaluation → Critical Analysis → Gap & Follow-up ─┬─ follow_up → Retriever (loop, bounded)
                                                                                      └─ synthesize ─┬─ Insights ────────────┬─ Report → END
                                                                                                     └─ Data Visualization ──┘
```

Insights and Data Visualization run in parallel (neither needs the other's output) and the Report waits for both.
Inside steps, the Retriever searches all providers at once and the Critical Analyst extracts claims from each source
in parallel.

```
```

The follow-up decision is deterministic. Research stops at the iteration limit, when the search, source or time
budget is exhausted, when no gap is worth pursuing, or when a round finds no new sources. See
[docs/architecture.md](docs/architecture.md) for agent contracts, the evidence model and the security design.

## Project structure

```
app.py                     entry point, navigation, home
app_pages/                 Streamlit pages (workspace, agents in action, results, library, settings);
                           not named `pages/` so Streamlit never falls back to legacy auto-navigation
src/config.py              settings from .env (secrets masked)
src/models/                research, evidence and run models (Pydantic)
src/orchestration/         LangGraph graph, typed state, budget tracker
src/agents/                planner, retriever, source_evaluator, critical_analyst, gap_analyst,
                           insight_generator, data_visualizer, report_builder, qa
src/search/                provider interface, Tavily/OpenAlex/Crossref/arXiv, demo & upload providers, HTTP safety
src/ingestion/             document extraction and chunking
src/evidence/              evidence store (dedup, syndication) and citations
src/analysis/              text heuristics, claims, evidence matrix
src/retrieval/             BM25
src/reporting/             Markdown/HTML/PDF rendering
src/database/              SQLite schema and repository
src/services/              research service, LLM client
src/ui/                    shared UI state, components (CSS skin), charts; views/ = results tabs
data/sample_research/      synthetic demo corpus
tests/                     pytest suite (mocked providers, fake LLM, network blocked)
docs/architecture.md
```

## Testing

`pytest` runs the offline suite (153 tests at this upgrade; use `pytest --collect-only` for the current count). An autouse fixture **fails any test that touches the network**; providers use
`httpx.MockTransport`, and the LLM is a fake OpenAI client. The tests cover question validation, plan
generation and schema, provider parsing (Tavily, OpenAlex, Crossref, arXiv), retries and rate limits, SSRF
blocking, document extraction, normalisation and dedup, syndication, claims and verbatim-quote validation, the
evidence matrix and contradictions, citation validation, conditional routing, iteration, search and source
limits, provider and agent failures, missing credentials, caching, persistence and history, report export,
Q&A citation validation, and prompt-injection handling.

## Known limitations

- Heuristic (demo/no-LLM) analysis uses wording cues. Claim clustering and polarity can miss paraphrased
  agreement or flag false contradictions, and those contradictions are labelled as heuristic. The LLM mode
  reviews each candidate.
- Academic results are usually abstracts only. This is shown per source and in the report.
- Retrieval is keyword-based (BM25); paraphrased questions may retrieve less well than with embeddings.
- Full-text fetching is limited to 6 pages per round and skips non-HTML content.
- Scanned PDFs need OCR (not included). Model cost estimates require configured input/output prices; they are not billing invoices.
- Public deployments require configured sign-in; explicit local mode uses one shared local administrator.

## Troubleshooting

- **"Web search unavailable"**: set `TAVILY_API_KEY` in `.env` and restart, or rely on academic sources.
- **Live runs return few sources**: widen the date range, enable more providers, or choose *Deep*.
- **LLM output rejected** (in the progress log): the app fell back to deterministic logic. Try a stronger model on the Settings page.
- **"You already have an investigation in progress"**: each user runs one at a time by default
  (`MAX_ACTIVE_RUNS_PER_USER`). Open it from **In progress** in the sidebar, stop it, or wait for it to finish.
- **A run is stuck as "running"** after the app stopped: running investigations send a heartbeat every `RUN_HEARTBEAT_SECONDS`; one without a heartbeat for `RUN_STALE_AFTER_SECONDS` is marked failed when the app next starts. Runs that are still alive on another instance are left alone.
- **Start fresh**: delete `data/research.db`.

## Recommended next steps

Hybrid BM25 plus embedding retrieval, LLM-assisted source evaluation with calibration studies, OCR, more providers
(Semantic Scholar, news APIs), scheduled re-runs to track how evidence changes, and automatic price lookup per model.

## Evidence-backed charts and claim integrity

The **Data Visualization Agent** is the eighth pipeline agent. The **Charts** tab shows numeric series from uploaded CSV rows, with exact values, units, source IDs, passage IDs, row locations and quotations. Download the underlying CSV to audit a chart. The cited report and Markdown/HTML/PDF exports include the numeric evidence as text, not embedded chart images.

Use a CSV such as `year,revenue (USD)` followed by rows containing actual extracted figures. Each chart uses one source and one compatible unit. Duplicate labels, conflicting units, nonfinite values and out-of-range percentages are rejected. Missing cells are omitted, never filled with zeros. Only simple year labels produce line charts; other categories use bars. Existing CSV uploads need to be uploaded again to retain structured row metadata. Web/PDF tables are not automatically converted into series yet. A narrative percentage can appear as a single indicator with its full quotation; percentages from unrelated sources are not combined. Synthetic demo figures remain labelled fictional.

The **Critical Analysis Agent** rejects model paraphrases that introduce numbers or units, change explicit negation, or remove forecast/uncertainty wording. Accepted claims retain the source quotation as their canonical text, with source-derived type and polarity. These checks improve quotation integrity; they do not prove that a source's claim is true or establish full semantic entailment.

## Budget accounting

Every actual LLM request, including a retry, consumes the per-run call allowance. Token reservations are atomic across parallel claim extraction calls. Before a request, a conservative allowance based on prompt UTF-8 bytes, response limit and framing is reserved. Provider-reported usage replaces that allowance on success; failed requests and responses without usage retain an explicitly **unreported** allowance because their billing is unknown. Conservative reservations can stop a run before the nominal token limit. The progress page separates observed, unreported and in-flight tokens.

Set `LLM_INPUT_USD_PER_MILLION` and `LLM_OUTPUT_USD_PER_MILLION` to the selected model's rates to enable a USD estimate. Update these when changing models; zero means unknown, not free. Estimates are partial if usage is missing. LLM request timeouts and retry waits use the remaining run time. Already-running search/fetch requests have their own HTTP timeout, so the run time budget is not a hard cancellation of all network work. Concurrency is bounded: each app process executes at most `MAX_CONCURRENT_RUNS` investigations at once, each user may have `MAX_ACTIVE_RUNS_PER_USER` queued or running, and new runs are refused once `MAX_QUEUED_RUNS` are active overall. There are no token or cost quotas per user.

## CI and deployment verification

[Deployment guide and verification checklist](docs/deployment.md) separates health checks from the authenticated workflow. A public URL and test account are needed to verify the actual hosted app; local tests cannot establish deployment readiness.

GitHub Actions installs the tested dependency constraints, checks dependency consistency, runs Ruff correctness checks, runs the offline tests and scans the working tree plus reachable Git history for credential candidates. Run the same checks locally:

```bash
python -m pip install -r requirements.txt -c constraints.txt
python -m pip check
ruff check .
pytest
python scripts/scan_secrets.py
```

The constraints snapshot records the development environment's package versions; CI must confirm installation on its own runner. Ruff deliberately checks syntax, undefined names and control-flow errors; it does not claim every style issue is resolved.

## Configurable LangSmith observability

Use `LANGSMITH_TRACING` as the master switch and `APP_API_TRACING` to control detailed request spans. Restart Streamlit after changes. Graph agents, OpenRouter calls and search/HTTP spans have been observed in the user's local APAC traces; switch-off, failure-mode and token-total verification remain pending.

See the [LangSmith guide](docs/observability.md) for setup, portal navigation, token counts, privacy and troubleshooting. The earlier 153-test regression result predates the observability integration.
