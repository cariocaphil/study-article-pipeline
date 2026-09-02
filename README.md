# Study Article Collection Doc Generator Pipeline

Given a topic (film, book, author, etc.), a source language, a translation
language, and your CEFR level, this pipeline searches the web for
native-language review articles, extracts vocabulary and expressions above
your level (with translations), and compiles everything into a printable PDF for language study.

## How it works

Five agents run in sequence, each owning one stage of the pipeline:

| Stage | Agent | File | Responsibility |
|-------|-------|------|-----------------|
| 1 | Search | `src/agents/search_agent.py` | Find candidate article URLs; validate reachability before returning |
| 2 | Filter | `src/agents/filter_agent.py` | Confirm each URL is a genuine review, fetch full text + author |
| 3 | Extract | `src/agents/extract_agent.py` | Pull vocabulary/constructions/idioms at or above your CEFR level; verify quotes and translations |
| 4 | Review | `src/agents/review_agent.py` | Independently audit extracted phrases for quality, drop low-quality items |
| 5 | Compile | `src/agents/compile_agent.py` | Produce the final `.pdf` |

`src/orchestrator.py` wires these together, handles CLI input, and enforces
the fallback rule: if fewer than 3 articles pass the filter stage, the
pipeline stops with a warning instead of padding the document with
low-quality matches.

All data passed between agents is validated through Pydantic models in
`src/schemas/article.py` (`Article`, `ExtractedPhrase`, `PipelineOutput`).

Several agents load evaluation criteria from skill files in
`.claude/skills/` at runtime (e.g. the review agent uses
`phrase-quality-reviewer.md` to flag proper nouns, topic derivatives, and
near-duplicates before phrases reach the final document).

### Validation tools

Some agents expose **client-side validation tools** — local Python functions
Claude can call during extraction. The agent runs a tool-use loop and only
keeps items that passed validation:

| Tool | Agent | What it checks |
|------|-------|----------------|
| `validate_url_reachable` | Search | URL passes SSRF checks; responds to HTTP HEAD (2xx/3xx) |
| `verify_quote` | Extract | `sentence_context` is a verbatim quote from the article |
| `validate_translation` | Extract | Translation is non-empty and not a lazy copy of the source phrase |

Search and filter agents also use Anthropic's server-executed `web_search`
tool. Tool implementations live in `src/tools/`.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- An [Anthropic API key](https://console.anthropic.com/) with access to
  `claude-sonnet-4-6` and credit balance for web search

## Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Create a `.env` file in the project root with your API key:

   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   This file is gitignored — never commit it.

3. Install Git pre-commit hooks (optional but recommended — runs Ruff format and
   check before each commit):

   ```bash
   uv run pre-commit install
   ```

## Usage

### Web app (recommended)

Launch the Streamlit UI:

```bash
uv run streamlit run app.py
```

Fill in the topic, source language, translation language, and your CEFR
level in the browser, then click **Generate study document**. Preview the
PDF in the browser and download it once the pipeline finishes.

### Command line

Run the orchestrator directly:

```bash
uv run python -m src.orchestrator "<topic>" <source_language> <translation_language> <cefr_level> [n_articles]
```

Example:

```bash
uv run python -m src.orchestrator "Entroncamento" portuguese german C1 5
```

Or, if you're using Claude/Cursor slash commands, use the `/find-articles`
command defined in `.claude/commands/find-articles.md`:

```
/find-articles "<topic>" <source_language> <translation_language> <cefr_level> [n_articles]
/find-articles "Entroncamento" portuguese german C1 5
```

Arguments (CLI and web app):

| Argument | Description | Example |
|----------|-------------|---------|
| `topic` | Film, book, play, album, or subject to search for | `"Amadeus"` |
| `topic_type` | Kind of work — disambiguates search (web app dropdown; CLI optional) | `theatre` |
| `source_language` | Language the review articles are written in | `portuguese` |
| `translation_language` | Language to translate extracted phrases into | `german` |
| `cefr_level` | Your CEFR level — only phrases at or above this level are kept | `C1` |
| `n_articles` | Number of candidate articles to search for (optional, default `5`) | `5` |

`topic_type` values: `film` (default), `series`, `book`, `theatre`, `album`.

## Output

Generated documents are saved to `output/`, named:

```
{topic}_{source_language}_{translation_language}_{cefr_level}.pdf
```

Each document includes, per article: title, author, source, and a table of
extracted phrases with sentence context, translation, category
(vocab/construction/idiom), and estimated CEFR level.

The Streamlit app previews the PDF inline and offers a download button.
CLI runs print the output path when complete.

## Container

Build the image with Podman or Docker:

```bash
podman build -t study-article-pipeline -f Containerfile .
# docker build -t study-article-pipeline -f Containerfile .
```

Run locally on port 8501 (pass your API key at runtime — do not bake it into the image):

```bash
podman run --rm -p 8501:8501 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  study-article-pipeline
```

Open [http://localhost:8501](http://localhost:8501).

To persist generated PDFs on the host, mount the `output/` directory:

```bash
podman run --rm -p 8501:8501 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v "$(pwd)/output:/app/output" \
  study-article-pipeline
```

The image installs DejaVu Sans so PDF generation works on Linux without bundling font files.

For Azure, build for **linux/amd64** (Container Apps runs AMD64 nodes):

```bash
podman build --platform linux/amd64 -t study-article-pipeline -f Containerfile .
# docker build --platform linux/amd64 -t study-article-pipeline -f Containerfile .
```

## Azure Container Apps

Manual deployment runbook for hosting the Streamlit app on [Azure Container Apps](https://learn.microsoft.com/azure/container-apps/overview) (ACA). Requires the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and an active subscription.

Set names once (adjust region and names as needed):

```bash
RESOURCE_GROUP=study-article-rg
LOCATION=westeurope
ACR_NAME=studyarticleacr          # globally unique, alphanumeric only
ENV_NAME=study-article-env
APP_NAME=study-article-app
IMAGE=study-article-pipeline:latest
```

### 1. Create resource group and Container Registry

```bash
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled false
```

### 2. Build and push a Linux AMD64 image

From the repo root, build for AMD64 and push to ACR:

```bash
az acr login --name "$ACR_NAME"

podman build --platform linux/amd64 \
  -t "${ACR_NAME}.azurecr.io/${IMAGE}" \
  -f Containerfile .
podman push "${ACR_NAME}.azurecr.io/${IMAGE}"
```

Docker equivalent:

```bash
docker build --platform linux/amd64 \
  -t "${ACR_NAME}.azurecr.io/${IMAGE}" \
  -f Containerfile .
docker push "${ACR_NAME}.azurecr.io/${IMAGE}"
```

### 3. Create Container Apps environment and app

```bash
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"

az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "${ACR_NAME}.azurecr.io/${IMAGE}" \
  --target-port 8501 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --system-assigned \
  --secrets anthropic-api-key=<your-anthropic-api-key> \
  --env-vars ANTHROPIC_API_KEY=secretref:anthropic-api-key
```

Replace `<your-anthropic-api-key>` with your key. Store it as a Container Apps secret — never commit it or bake it into the image.

### 4. Grant managed identity access to ACR

The container app uses a system-assigned managed identity to pull from ACR (admin user stays disabled):

```bash
APP_ID=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query identity.principalId -o tsv)

ACR_ID=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

az role assignment create \
  --assignee "$APP_ID" \
  --role AcrPull \
  --scope "$ACR_ID"
```

If the app was created before the role assignment, update it so the revision picks up registry auth:

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "${ACR_NAME}.azurecr.io/${IMAGE}"
```

### 5. Verify

Print the public HTTPS URL:

```bash
az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv
```

Open `https://<fqdn>` in a browser. The app serves Streamlit on port 8501 with external HTTPS ingress terminated by ACA.

Run an end-to-end pipeline test: enter a topic, languages, and CEFR level, then confirm the PDF preview and download work. Check revision logs if anything fails:

```bash
az containerapp logs show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --follow
```

### Updating the deployed image

After code changes, rebuild for AMD64, push a new tag, and update the app:

```bash
podman build --platform linux/amd64 \
  -t "${ACR_NAME}.azurecr.io/${IMAGE}" \
  -f Containerfile .
podman push "${ACR_NAME}.azurecr.io/${IMAGE}"

az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "${ACR_NAME}.azurecr.io/${IMAGE}"
```

### Continuous deployment

Merges to `main` deploy automatically after CI passes. The workflow
(`.github/workflows/deploy.yml`) runs on successful completion of the CI
workflow, builds a **linux/amd64** image tagged with the commit SHA, pushes to
ACR, and updates the Container App.

One-time Azure and GitHub setup:

1. Create a Microsoft Entra application for GitHub Actions OIDC login.
2. Add a federated credential for `repo:<owner>/<repo>:ref:refs/heads/main`.
3. Grant the app **AcrPush** on the registry and **Contributor** on the resource group.
4. Add GitHub repository secrets:
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`

`ANTHROPIC_API_KEY` stays on the Container App as a secret (configured during
PR 33 manual deploy) — the CD workflow only updates the container image.

## Testing

Run the full test suite:

```bash
uv run pytest
```

Skip slow tests that call the live Anthropic API:

```bash
uv run pytest -m "not slow"
```

Run lint checks locally (see also `AGENTS.md`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Or install pre-commit hooks once (`uv run pre-commit install`) so Ruff runs
automatically on each commit.

CI runs on pushes and pull requests to `main` via GitHub Actions
(`.github/workflows/ci.yml`): Ruff lint/format, Pyright type checking, fast
pytest, and offline eval smoke tests. No API key is required.

Tests cover agents, validation tools, JSON repair (`json_utils`), the
Streamlit UI (`AppTest`), and deterministic evals (`tests/test_evals.py`).

Run the quote faithfulness eval on a saved pipeline output:

```bash
uv run python -m evals.runners.run_evals \
  --suite quote_faithfulness \
  --input evals/datasets/fixtures/sample_pipeline_output.json
```

Run filter classification offline against cached predictions:

```bash
uv run python -m evals.runners.run_evals \
  --suite filter_classification \
  --input evals/datasets/filter/urls.jsonl \
  --predictions evals/datasets/fixtures/filter_predictions.jsonl
```

Add `--live` to score the real filter agent (requires `ANTHROPIC_API_KEY`).

Run review actions offline against cached predictions:

```bash
uv run python -m evals.runners.run_evals \
  --suite review_actions \
  --input evals/datasets/review/phrase_lists.jsonl \
  --predictions evals/datasets/fixtures/review_predictions.jsonl
```

Add `--live` to score the real review agent (requires `ANTHROPIC_API_KEY`).

Run extract phrase recall offline against cached predictions:

```bash
uv run python -m evals.runners.run_evals \
  --suite extract_phrase_recall \
  --input evals/datasets/extract/gold_phrases.jsonl \
  --predictions evals/datasets/fixtures/extract_predictions.jsonl
```

Add `--live` to score the real extract agent (requires `ANTHROPIC_API_KEY`).

Gold phrases are labeled manually for fixed article excerpts. Each case lists
phrases a human annotator would expect the extract agent to surface at the given
CEFR level. Recall is the fraction of gold phrases found in the agent output.

Run translation quality offline against cached judge predictions:

```bash
uv run python -m evals.runners.run_evals \
  --suite translation_quality \
  --input evals/datasets/translation/phrases.jsonl \
  --predictions evals/datasets/fixtures/translation_judge_predictions.jsonl
```

Add `--live` to score with the LLM judge (requires `ANTHROPIC_API_KEY`).

Run search URL recall offline against cached predictions:

```bash
uv run python -m evals.runners.run_evals \
  --suite search_url_recall \
  --input evals/datasets/search/gold_urls.jsonl \
  --predictions evals/datasets/fixtures/search_predictions.jsonl
```

Add `--live` to score the real search agent (requires `ANTHROPIC_API_KEY`).

Gold URLs are stable review links a human verified for each topic. Recall
measures whether search returned those known-good candidates (filter still
judges page content afterward).

Run composite pipeline quality on a saved `PipelineOutput`:

```bash
uv run python -m evals.runners.run_evals \
  --suite pipeline_quality \
  --input evals/datasets/fixtures/sample_pipeline_output.json
```

Use `evals/datasets/fixtures/pipeline_output_good.json` for a passing example.

Compare two saved eval runs:

```bash
uv run python -m evals.runners.compare_runs \
  --baseline evals/results/BASELINE_RUN_ID \
  --candidate evals/results/CANDIDATE_RUN_ID
```

Results are saved under `evals/results/` (gitignored).

## Project structure

```
app.py                        # Streamlit web UI entry point
.github/
├── workflows/
│   ├── ci.yml                # Ruff, Pyright, pytest, offline evals
│   └── deploy.yml            # CD to Azure Container Apps after CI on main
evals/
├── datasets/
│   ├── filter/urls.jsonl       # labeled accept/reject URL dataset
│   ├── extract/gold_phrases.jsonl  # human-labeled gold phrases for fixed excerpts
│   ├── review/phrase_lists.jsonl  # labeled keep/review/remove phrase lists
│   ├── translation/phrases.jsonl  # human-labeled translation adequacy cases
│   ├── search/gold_urls.jsonl  # stable gold review URLs per topic
│   └── fixtures/               # sample PipelineOutput + cached predictions
├── evaluators/                 # quote_faithfulness, filter_classification, review_actions, extract_phrase_recall, translation_quality, search_url_recall, pipeline_quality
└── runners/
    ├── run_evals.py            # CLI entry point
    └── compare_runs.py         # diff scores between two saved runs
.claude/
├── commands/
│   └── find-articles.md      # slash command definition
└── skills/                   # agent evaluation criteria (loaded at runtime)
    ├── article-filter-criteria.md   # injected in filter_agent.py
    ├── cefr-extraction-guide.md     # injected in extract_agent.py
    ├── pdf-formatted.md             # document layout reference for compile_agent.py
    ├── phrase-quality-reviewer.md   # injected in review_agent.py
    └── translation-adequacy-rubric.md  # injected in translation quality judge
src/
├── orchestrator.py           # wires agents together, CLI entry point
├── agents/
│   ├── search_agent.py       # finds candidate article URLs (web_search + URL validation)
│   ├── filter_agent.py       # validates + fetches article content
│   ├── extract_agent.py      # extracts phrases (quote + translation validation)
│   ├── review_agent.py       # audits phrase quality, drops low-value items
│   └── compile_agent.py      # generates the PDF
├── tools/                    # client-side validation tools used by agents
│   ├── validate_url_reachable.py
│   ├── url_safety.py
│   ├── verify_quote.py
│   ├── validate_translation.py
│   └── validate_topic.py
├── schemas/
│   └── article.py            # Pydantic models shared between agents
└── utils/
    ├── __init__.py           # load_skill() helper
    ├── anthropic_retry.py    # retry transient Anthropic API failures
    └── json_utils.py         # robust JSON extraction from LLM responses
tests/
├── conftest.py               # shared fixtures (API client, sample text/phrases)
├── test_app.py               # Streamlit UI tests (AppTest)
├── test_anthropic_retry.py
├── test_compile_agent.py
├── test_evals.py             # deterministic eval harness tests
├── test_extract_agent.py
├── test_filter_agent.py
├── test_json_utils.py        # JSON repair/parsing tests
├── test_orchestrator.py      # topic input guardrails
├── test_review_agent.py
├── test_search_agent.py
├── test_validate_translation.py
├── test_validate_topic.py
├── test_validate_url_reachable.py
├── test_url_safety.py
└── test_verify_quote.py
output/                        # generated PDF files land here
```

## Roadmap

PR numbers match merged GitHub pull requests. Future work continues from **PR 34**.

### Initial Setup ✅

- [x] Initialize Python project with uv
- [x] Set up project structure and `.env` configuration

### PR 1 — Pydantic Schema ✅

- [x] Add `Article`, `ExtractedPhrase`, and `PipelineOutput` models
- [x] Add CEFR level and phrase category enums

### PR 2 — Search Agent ✅

- [x] Add search agent with Anthropic web search
- [x] Return candidate article URLs as structured JSON

### PR 3 — Filter Agent ✅

- [x] Add filter agent to validate and fetch article content
- [x] Extract title, author, source, and full text per URL

### PR 4 — Extract Agent ✅

- [x] Add extract agent for vocabulary, constructions, and idioms
- [x] Apply CEFR level floor filtering

### PR 5 — Compile Agent ✅

- [x] Add compile agent with `python-docx`
- [x] Generate printable study documents per article

### PR 6 — Orchestrator ✅

- [x] Wire agents together in sequence
- [x] Add CLI entry point and slash command
- [x] Enforce minimum article fallback rule (≥ 3 filtered articles)
- [x] Add robust JSON parsing for LLM responses (`json_utils`)

### PR 7 — Streamlit Frontend ✅

- [x] Add Streamlit UI (`app.py`)
- [x] Wire form inputs to orchestrator pipeline
- [x] Add download button for generated `.docx`
- [x] Add AppTest coverage for layout and pipeline mocking

### PR 8 — Post-Run Hook ✅

- [x] Add post-run hook to open latest `.docx` after CLI runs
- [x] Document macOS / Linux / Windows open commands

### PR 9 — Claude Code Skills ✅

- [x] Add skill files under `.claude/skills/`
- [x] Inject filter, extract, and review criteria at runtime

### PR 10 — Review Agent ✅

- [x] Add review agent for phrase quality checks
- [x] Add `phrase-quality-reviewer` skill
- [x] Integrate review step between extract and compile
- [x] Flag proper nouns, topic derivatives, and near-duplicates

### PR 11 — Agent Test Suite ✅

- [x] Add pytest configuration and shared fixtures
- [x] Add unit tests for JSON repair and compile agent
- [x] Add slow integration tests for live Anthropic API calls
- [x] Add Streamlit AppTest coverage

### PR 12 — Client-Side Validation Tools ✅

- [x] Add `validate_url_reachable` for search agent
- [x] Add `verify_quote` for extract agent
- [x] Add `validate_translation` for extract agent
- [x] Wire client-side tool-use loops into search and extract agents
- [x] Add continuation retry when extract agent returns prose instead of JSON
- [x] Add mocked tool-loop tests for search and extract agents

### PR 13 — Eval: Quote Faithfulness ✅

- [x] Add `evals/` evaluation harness (`EvalResult`, `EvalReport`, CLI runner)
- [x] Add quote faithfulness evaluator (verbatim `sentence_context` check)
- [x] Add sample `PipelineOutput` fixture and deterministic tests
- [x] Store eval results under `evals/results/` (`report.json`, `scores.json`, `failures.jsonl`)

### PR 14 — Eval: Filter Classification ✅

- [x] Add labeled URL golden dataset (`evals/datasets/filter/urls.jsonl`)
- [x] Add filter classification evaluator (accuracy, precision, recall, F1)
- [x] Support offline scoring via cached predictions
- [x] Support live scoring via `--live` (calls `filter_agent` per URL)

### PR 15 — Eval: Review Actions ✅

- [x] Add golden phrase-list dataset with expected keep/review/remove labels
- [x] Add review actions evaluator (removal precision/recall, action accuracy)
- [x] Support offline scoring via cached predictions
- [x] Support live scoring via `--live` (calls `review_agent` per phrase list)
- [x] Add deterministic tests and CLI registration

### PR 16 — Eval: Extract Phrase Recall ✅

- [x] Add human-labeled gold phrases for fixed article excerpts
- [x] Add extract phrase recall evaluator against gold dataset
- [x] Support offline scoring via cached predictions
- [x] Support live scoring via `--live` (calls `extract_agent` per excerpt)
- [x] Document labeling process and add deterministic tests

### PR 17 — Eval: Translation Quality & Regression Comparison ✅

- [x] Add translation adequacy rubric and LLM-as-judge evaluator
- [x] Add `compare_runs` CLI to diff scores across eval runs
- [x] Support live LLM judge runs via `--live` (local, API key required)

### PR 18 — Eval: Search URL Recall ✅

- [x] Add stable gold URL dataset for fixed search topics
- [x] Add search URL recall evaluator against gold links
- [x] Support offline scoring via cached predictions
- [x] Support live scoring via `--live` (calls `search_agent` per topic)

### PR 19 — Eval: Pipeline Quality ✅

- [x] Add composite pipeline quality evaluator on saved `PipelineOutput`
- [x] Score structure, phrase coverage, quote faithfulness, translation validity, and level-floor compliance
- [x] Add passing and failing fixtures plus deterministic tests
- [x] Register `pipeline_quality` suite in the eval CLI

### PR 20 — Input Guardrails ✅

- [x] Add `validate_topic()` client-side tool
- [x] Reject empty, oversized, or unsafe topic strings in the orchestrator
- [x] Align CLI validation with existing Streamlit checks

### PR 21 — Continuous Integration ✅

- [x] Add GitHub Actions workflow
- [x] Set up Python and uv in CI
- [x] Run fast pytest suite on pushes and pull requests (`pytest -m "not slow"`)
- [x] Run deterministic evals in CI (no API key required)
- [x] Add linting with Ruff

### PR 22 — Topic Type Disambiguation ✅

- [x] Add `TopicType` enum (`film`, `series`, `book`, `theatre`, `album`)
- [x] Add topic type dropdown to Streamlit UI
- [x] Steer search agent prompts by topic type
- [x] Support optional `topic_type` in CLI and store on `PipelineOutput`
- [x] Add pre-run confirmation summary card in Streamlit UI

### PR 23 — Pipeline Observability ✅

- [x] Replace `print()` with stdlib `logging` across agents, tools, and orchestrator
- [x] Add per-run ID and stage timing (search, filter, extract, compile)
- [x] Log Anthropic API token usage on agent calls
- [x] Add user-facing error handling in Streamlit (sanitized messages, server-side tracebacks)
- [x] Add post-run summary in Streamlit (articles, phrases, elapsed time, tokens)
- [x] Replace generic spinner with per-stage progress via `st.status`

### PR 24 — Strict Typing ✅

- [x] Add Pyright with `standard` type checking in `pyproject.toml`
- [x] Fix type errors in pipeline source code, eval harness, and tests
- [x] Add shared Anthropic typing helpers (`message_text`, `FilteredArticle`)
- [x] Run Pyright in CI alongside Ruff

### PR 25 — PDF Output ✅

- [x] Replace DOCX generation with direct PDF generation (no intermediate Word file)
- [x] Preserve current document structure (headings, articles, vocabulary sections, margins)
- [x] Remove post-run DOCX hook and `python-docx` dependency
- [x] Add in-browser PDF preview (`st.pdf`) and Download PDF in Streamlit
- [x] Persist generated PDF across Streamlit reruns via session state
- [x] Update tests, filenames, and docs for PDF as the canonical format

### PR 26 — Trust Boundary ✅

- [x] Add shared helper to wrap retrieved article content as untrusted data
- [x] Apply trust-boundary preamble and delimiters in filter, extract, and review agents
- [x] Add unit tests for wrapping and prompt usage
- [x] Document trust boundaries in CLAUDE.md (complements PR 20 input guardrails)

### PR 27 — URL Safety ✅

- [x] Add `is_safe_fetch_url()` to block private, local, and non-http(s) URLs
- [x] Run SSRF checks in `validate_url_reachable` before outbound HTTP HEAD
- [x] Add unit tests for blocked URLs (no network I/O)
- [x] Document URL safety in CLAUDE.md trust boundaries

### PR 28 — Safe Markdown Output ✅

- [x] Escape user topic before rendering in Streamlit confirmation markdown
- [x] Add unit tests for markdown metacharacter neutralization
- [x] Document Streamlit output safety in CLAUDE.md trust boundaries

### PR 29 — API Retry ✅

- [x] Add `create_message_with_retry()` for transient Anthropic API failures
- [x] Use retry wrapper in search, filter, extract, and review agents
- [x] Improve Streamlit error messages after exhausted API retries
- [x] Add unit tests for retry behavior and user-facing API errors

### PR 30 — Enforce Python Formatting ✅

- [x] Add `.pre-commit-config.yaml` with Ruff format and check hooks
- [x] Add `pre-commit` to dev dependencies
- [x] Document hook setup in README and `AGENTS.md`
- [x] Verify hooks catch and fix misformatted Python locally

### PR 31 — PDF Footer and Page Numbers ✅

- [x] Add document title and page numbers to every PDF page footer
- [x] Truncate long titles in the footer with an ellipsis
- [x] Update PDF formatting skill and add compile agent tests

### PR 32 — Containerization ✅

- [x] Add Containerfile for the Streamlit app
- [x] Package the application and its dependencies
- [x] Build and run locally as a container
- [x] Expose Streamlit on port 8501
- [x] Document the local container workflow

### PR 33 — Azure Container Apps Deployment ✅

- [x] Create Azure resource group and Container Registry
- [x] Build a Linux AMD64 container image
- [x] Push the image to ACR
- [x] Create a Container Apps Environment and Container App
- [x] Configure managed-identity access to ACR
- [x] Configure external HTTPS ingress on port 8501
- [x] Verify the app through its public Azure URL

### PR 34 — Continuous Deployment

- [x] Create Microsoft Entra application for GitHub Actions
- [x] Configure GitHub OIDC federated credential for `main`
- [x] Grant deployment identity `Contributor` and `AcrPush` access
- [x] Configure Azure identifiers as GitHub Actions secrets
- [x] Add deployment workflow (build → push SHA-tagged image → deploy to ACA)
- [x] Trigger CD after successful CI on `main`
- [ ] Verify the complete automated deployment flow

## Notes

- Web search results and LLM parsing are inherently non-deterministic —
  re-running the same query may surface different articles.
- The pipeline stops early (rather than producing a thin document) if fewer
  than 3 articles pass the filter stage for a given topic.
