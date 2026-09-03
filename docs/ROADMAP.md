# Roadmap

Build history for the Study Article Collection pipeline.

PR numbers match merged GitHub pull requests. Future work continues from **PR 48**.

The README keeps a short **Status** summary; this file holds the full checklist.

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

### PR 34 — Continuous Deployment ✅

- [x] Create Microsoft Entra application for GitHub Actions
- [x] Configure GitHub OIDC federated credential for `main`
- [x] Grant deployment identity `Contributor` and `AcrPush` access
- [x] Configure Azure identifiers as GitHub Actions secrets
- [x] Add deployment workflow (build → push SHA-tagged image → deploy to ACA)
- [x] Trigger CD after successful CI on `main`
- [x] Verify the complete automated deployment flow

### PR 35 — Authentication and Quotas ✅

- [x] Enable ACA Easy Auth (Microsoft Entra ID)
- [x] Add Azure Table Storage for daily per-user generation counts
- [x] Parse authenticated user identity from ACA headers in Streamlit
- [x] Enforce daily quota before pipeline runs
- [x] Add unit tests and document Azure/local setup
- [x] Verify auth and quota enforcement on the public deployment

### PR 36 — Google Authentication ✅

- [x] Add Google as an ACA Easy Auth identity provider
- [x] Parse Google identity claims and add provider login/sign-out links
- [x] Namespace Google user IDs for quota tracking (`google:{sub}`)
- [ ] Verify identity + quota behavior with Google users on the public deployment

### PR 37 — Authentication provider selection ✅

- [x] Switch ACA auth to **Allow unauthenticated access** (app-level gate unchanged)
- [x] Add login landing with Microsoft and Google sign-in buttons
- [x] Add `login_url()` / `logout_url()` with post-login and post-logout redirects
- [x] Update tests and document multi-provider login UX
- [x] Verify login landing and both providers on the public deployment

### PR 38 — Generation UX ✅

- [x] Rename displayed app title to **Study Article Collection Generator.**
- [x] Default article count in the web UI to **3**
- [x] Disable form controls after **Generate study document** is clicked
- [x] Keep controls disabled during confirmation and pipeline execution
- [x] Re-enable controls after success, failure, or quota error
- [x] Add AppTest coverage for locked and restored widget states

### PR 39 — Topic disambiguation (release year) ✅

- [x] Encourage optional release/premiere year in the Topic field (web app help text)
- [x] Parse trailing `(19xx|20xx)` years from topic strings
- [x] Inject year + content-type disambiguation guidance into search prompts
- [x] Apply year disambiguation for all content types (film, series, book, theatre, album)
- [x] Add unit and search-prompt regression tests (including `Madre (2017)` case)

### PR 40 — Eval: Madre search disambiguation ✅

- [x] Add labeled `Madre (2017)` case to `search_url_recall` gold dataset
- [x] Support optional `forbidden_urls` and `forbidden_url_substrings` on search cases
- [x] Fail when predictions include *mother!* / `madre!` / `¡madre!` alternate-work markers
- [x] Pass `topic_type` through live search-eval collection
- [x] Update offline fixtures and regression tests

### PR 41 — Extract LLM prompts ✅

- [x] Move agent and translation-judge prompts into `src/prompts/*.txt`
- [x] Add `load_prompt()` for version-controlled templates with `str.format` interpolation
- [x] Rewire search, filter, extract, review, and translation-judge call sites
- [x] Preserve prompt text and runtime behavior (no prompt rewriting)
- [x] Add `tests/test_prompts.py` for loading and rendered-prompt checks

### PR 42 — Repo presentation ✅

- [x] Move completed PR history into `docs/ROADMAP.md`
- [x] Replace README roadmap with a short Status stub and link
- [x] Rewrite README front matter (why / architecture / demo / evals narrative)
- [x] Add sample PDF proof asset under `docs/samples/`
- [x] Optional demo GIF/screenshot when available

### PR 43 — Eval: Document quality ✅

- [x] Add document-quality rubric skill and LLM-as-judge prompt
- [x] Add labeled complete-document cases and offline judge predictions
- [x] Score structure, relevance, usefulness, phrases, translations, faithfulness, duplication
- [x] Register `document_quality` suite with offline fixtures and `--live` support
- [x] Cover loading, parsing, scoring, and failure handling in tests

### PR 44 — Codecov coverage ✅

- [x] Add `pytest-cov` dev dependency
- [x] Run pytest with `--cov=src --cov=evals` in CI and upload `coverage.xml` to Codecov
- [x] Add CI and Codecov status badges to README header
- [x] Document `CODECOV_TOKEN` repository secret for GitHub Actions

### PR 45 — Commit uv lockfile ✅

- [x] Stop gitignoring `uv.lock` and commit the resolved lockfile
- [x] Use `uv sync --frozen` in CI and the Containerfile for reproducible installs
- [x] Document lockfile update workflow in README setup

### PR 46 — Dependabot ✅

- [x] Add `.github/dependabot.yml` for `uv` and `github-actions` ecosystems
- [x] Schedule weekly update checks with a modest open-PR limit
- [x] Document Dependabot in README and ROADMAP

### PR 47 — Security scanning ✅

- [x] Add warn-only `uv audit --frozen` job to CI (lockfile / OSV)
- [x] Scan the built container image with Trivy on deploy (CRITICAL/HIGH, warn-only)
- [x] Document security scanning in README and ROADMAP
