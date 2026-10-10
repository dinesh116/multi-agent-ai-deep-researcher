# LangSmith tracing guide

## Configuration

LangSmith observes the research workflow and instrumented requests; it does not replace OpenRouter, search providers or the application's budget enforcement.

| LANGSMITH_TRACING | APP_API_TRACING | Behavior |
|---|---|---|
| false | either | Research tracing disabled |
| true | false | Automatic graph/agent tracing; application request spans disabled |
| true | true | Graph/agent tracing and detailed request spans |

The master switch defaults to false when absent. `APP_API_TRACING` defaults to true, but only has an effect when the master switch is enabled. These settings apply to this application's instrumentation, not arbitrary third-party instrumentation. Fully stop and restart Streamlit after configuration changes.

Local `.env` example (replace the placeholder privately):

```dotenv
LANGSMITH_TRACING=true
APP_API_TRACING=true
LANGSMITH_PROJECT=deep-researcher-local
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
# LANGSMITH_WORKSPACE_ID=your_workspace_id
```

Choose the endpoint for the workspace's region, not your physical location. The example is for the APAC portal at `https://apac.smith.langchain.com`. Supply a workspace ID only when needed for key/workspace selection; do not substitute an organization or tracing-project ID.

The SDK is declared in the runtime dependencies. Install from the project folder with `uv pip install -r requirements.txt -c constraints.txt` after activating the virtual environment. LangSmith variables are read from the environment directly; they are not all fields of the application's `Settings` dataclass. The existing `.env` loader does not override variables already present in the process environment.

For deployment, put the variables at the top level of Streamlit Secrets, before `[auth]` or other TOML tables. Use TOML assignments such as `LANGSMITH_TRACING = "true"`. Keep local and deployed project names distinct. Actual credential files must remain private and ignored by Git.

## Inspecting a research trace

1. Run an investigation in the research application. Use live mode with LLM enabled to exercise model requests; demo mode normally does not make model requests.
2. In the LangSmith portal, click **Tracing**, then your configured project, such as `deep-researcher-local`.
3. Select **Traces** and open the latest **research-investigation** row.
4. Expand the execution tree to inspect `planner`, `retriever`, `source_evaluator`, `critical_analyst`, `gap_analyst`, `insight_generator`, `data_visualizer` and `report_builder`. Routing nodes and follow-up rounds can also appear. Collapse a busy retriever branch to reach later agents.
5. Look inside the agent branches for request spans:

| Span | Meaning |
|---|---|
| `openrouter.request` | One attempted model request; retries produce separate spans |
| `search.provider` | A provider search, including cache and budget outcomes |
| `http.get_json`, `http.post_json`, `http.get_text` | A logical provider HTTP operation |
| `http.request_attempt` | An individual HTTP attempt inside the retry loop |
| `http.safe_fetch`, `http.fetch_attempt` | A page fetch and its individual redirect hops |

Model spans may be displayed using the model identifier. The **Runs** tab lists individual spans; its count includes agents, routing and HTTP operations, not just investigations or model calls. Parent and child durations overlap, particularly for parallel jobs, so do not add all displayed durations together.

## Finding token counts

Select a model span and open **Attributes**. Inspect:

```text
metadata
  request_metrics
    usage_metadata
      input_tokens
      output_tokens
      total_tokens
```

The exact visual nesting of metadata may vary with the portal layout. A visible token badge such as `1.445K` is approximately 1,445 tokens for that model call. If usage was not returned by the provider, these fields may be absent or null; absence does not mean zero usage. Default output hiding can leave the Input and Output tabs empty while safe metrics remain in metadata. Automatic aggregate token/cost dashboards are not guaranteed for custom spans; do not sum both a parent aggregate and its child model calls.

For the application's per-investigation totals, open the research app at `http://localhost:8501`, select the investigation from **Research library** if necessary, then navigate to **Agents in action** in the app sidebar. This is an application page, not a LangSmith portal link. Its budget display distinguishes:

- **Observed tokens:** usage actually reported by the provider.
- **Unreported allowance:** a conservative charge for requests whose usage is unknown; it is not a measured token count.
- **In-flight tokens:** reservations for ongoing requests.

USD estimates require the configured model's input/output prices. They are estimates, not billing invoices. LangSmith does not replace the application's budget tracker.

## Privacy and failure behavior

Custom spans omit function arguments, prompts, response bodies, search queries, URLs, headers, uploaded content and credentials. They include operation names, safe outcomes/counts, attempt numbers, model identifiers and reported token usage. Research graph metadata includes the opaque research run ID, mode and depth.

Keep input/output hiding enabled for private workloads. It defaults to true in configuration, but an explicit environment setting can override that default. These flags do not redact metadata or existing graph error strings. Exception details in pre-existing graph errors still need review before tracing sensitive workloads. Failed custom requests record the exception class; safe success metrics are not guaranteed on failure paths.

The observability module isolates tracing setup and cleanup errors from research execution. SDK background export failures can still produce warnings, and tracing has some overhead. The behavior when telemetry is unavailable has not yet been verified end to end.

## Troubleshooting

### Waiting for traces or an empty project list

Run a fresh investigation after restarting the app. Check the project name and time filter. A portal waiting indicator does not prove successful delivery. Inspect the terminal for export errors.

### HTTP 403 Forbidden

Check the region endpoint, the full API key, access to the intended workspace, and any conflicting process environment/Streamlit Secrets settings. A shortened key shown in the portal table cannot be used. The full key is shown only on creation; create a replacement if it was not saved, then revoke the old one after validating the replacement. Key prefix alone is not proof of validity or invalidity. If workspace selection is required, use the workspace ID, not an organization/project ID. Do not print or share keys while diagnosing errors.

During this session, tracing succeeded after the user replaced the key and restarted. That sequence does not conclusively establish the earlier 403's root cause.

### App fails to import copy_context

`copy_context` must be imported from Python's `contextvars` module. An initial implementation imported it from `contextlib`; that mistake was corrected. Static lint/syntax checks did not detect the runtime import error.

## Verification record — 11 October 2026

Confirmed by user-provided screenshots from the local app and APAC portal:

- A successful initial graph trace reached `deep-researcher-local`.
- An updated `research-investigation` trace appeared, with visible planner/retriever branches and model usage.
- Additional screenshots showed `openrouter.request`, provider searches, HTTP operations, and later agent spans.
- Visible request spans were attached within the research trace; this is not an exhaustive verification of every parallel request.

Still pending:

- Reconcile per-call and whole-run token totals with provider usage/billing.
- Verify retries and exhausted budgets under controlled failures.
- Verify no research traces are exported with the master switch off.
- Verify graph-only behavior with detailed API tracing off.
- Verify research completion when LangSmith is unavailable.
- Run automated regressions for the observability changes; earlier 153-test results predate this integration.
- Verify the public deployment's authenticated workflow and tracing.

No additional live requests or tests were executed for this documentation update.
