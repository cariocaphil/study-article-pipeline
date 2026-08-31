# Study Article Collection Doc Generator Pipeline

Given a topic (film, book, author, etc.), a source language, a translation
language, and your CEFR level, this pipeline searches the web for
native-language review articles, extracts vocabulary and expressions above
your level (with translations), and compiles everything into a printable
Word document for language study.

## How it works

Five agents run in sequence, each owning one stage of the pipeline:

| Stage | Agent | File | Responsibility |
|-------|-------|------|-----------------|
| 1 | Search | `src/agents/search_agent.py` | Find candidate article URLs; validate reachability before returning |
| 2 | Filter | `src/agents/filter_agent.py` | Confirm each URL is a genuine review, fetch full text + author |
| 3 | Extract | `src/agents/extract_agent.py` | Pull vocabulary/constructions/idioms at or above your CEFR level; verify quotes and translations |
| 4 | Review | `src/agents/review_agent.py` | Independently audit extracted phrases for quality, drop low-quality items |
| 5 | Compile | `src/agents/compile_agent.py` | Produce the final `.docx` |

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
| `validate_url_reachable` | Search | URL responds to an HTTP HEAD request (2xx/3xx) |
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

## Usage

### Web app (recommended)

Launch the Streamlit UI:

```bash
uv run streamlit run app.py
```

Fill in the topic, source language, translation language, and your CEFR
level in the browser, then click **Generate study document** and download
the resulting `.docx` once the pipeline finishes.

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
| `topic` | Film, book, author, or subject to search for | `"Entroncamento"` |
| `source_language` | Language the review articles are written in | `portuguese` |
| `translation_language` | Language to translate extracted phrases into | `german` |
| `cefr_level` | Your CEFR level — only phrases at or above this level are kept | `C1` |
| `n_articles` | Number of candidate articles to search for (optional, default `5`) | `5` |

## Output

Generated documents are saved to `output/`, named:

```
{topic}_{source_language}_{translation_language}_{cefr_level}.docx
```

Each document includes, per article: title, author, source, and a table of
extracted phrases with sentence context, translation, category
(vocab/construction/idiom), and estimated CEFR level.

After a successful CLI run, the orchestrator triggers a post-run hook
(`.claude/hooks/post-run.sh`) that opens the most recently generated
`.docx` in `output/`. On macOS this uses `open`; on Linux use `xdg-open`,
on Windows use `start` (edit the script if needed). The Streamlit app does
not auto-open files — use the download button instead.

## Testing

Run the full test suite:

```bash
uv run pytest
```

Skip slow tests that call the live Anthropic API:

```bash
uv run pytest -m "not slow"
```

Run lint checks locally:

```bash
uv run ruff check .
uv run ruff format --check .
```

CI runs on pushes and pull requests to `main` via GitHub Actions
(`.github/workflows/ci.yml`): Ruff lint/format, fast pytest, and offline
eval smoke tests. No API key is required.

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
└── workflows/ci.yml          # GitHub Actions: Ruff, pytest, offline evals
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
├── hooks/
│   └── post-run.sh           # opens latest .docx after CLI pipeline run
└── skills/                   # agent evaluation criteria (loaded at runtime)
    ├── article-filter-criteria.md   # injected in filter_agent.py
    ├── cefr-extraction-guide.md     # injected in extract_agent.py
    ├── docx-formatted.md            # document layout reference for compile_agent.py
    ├── phrase-quality-reviewer.md   # injected in review_agent.py
    └── translation-adequacy-rubric.md  # injected in translation quality judge
src/
├── orchestrator.py           # wires agents together, CLI entry point
├── agents/
│   ├── search_agent.py       # finds candidate article URLs (web_search + URL validation)
│   ├── filter_agent.py       # validates + fetches article content
│   ├── extract_agent.py      # extracts phrases (quote + translation validation)
│   ├── review_agent.py       # audits phrase quality, drops low-value items
│   └── compile_agent.py      # generates the .docx
├── tools/                    # client-side validation tools used by agents
│   ├── validate_url_reachable.py
│   ├── verify_quote.py
│   ├── validate_translation.py
│   └── validate_topic.py
├── schemas/
│   └── article.py            # Pydantic models shared between agents
└── utils/
    ├── __init__.py           # load_skill() helper
    └── json_utils.py         # robust JSON extraction from LLM responses
tests/
├── conftest.py               # shared fixtures (API client, sample text/phrases)
├── test_app.py               # Streamlit UI tests (AppTest)
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
└── test_verify_quote.py
output/                        # generated .docx files land here
```

## Roadmap

PR numbers match merged GitHub pull requests. Future work continues from **PR 22**.

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

### PR 22 — Containerization

- [ ] Add Containerfile for the Streamlit app
- [ ] Package the application and its dependencies
- [ ] Build and run locally as a container
- [ ] Expose Streamlit on port 8501
- [ ] Document the local container workflow

### PR 23 — Azure Container Apps Deployment

- [ ] Create Azure resource group and Container Registry
- [ ] Build a Linux AMD64 container image
- [ ] Push the image to ACR
- [ ] Create a Container Apps Environment and Container App
- [ ] Configure managed-identity access to ACR
- [ ] Configure external HTTPS ingress on port 8501
- [ ] Verify the app through its public Azure URL

### PR 24 — Continuous Deployment

- [ ] Create Microsoft Entra application for GitHub Actions
- [ ] Configure GitHub OIDC federated credential for `main`
- [ ] Grant deployment identity `Contributor` and `AcrPush` access
- [ ] Configure Azure identifiers as GitHub Actions secrets
- [ ] Add deployment workflow (build → push SHA-tagged image → deploy to ACA)
- [ ] Trigger CD after successful CI on `main`
- [ ] Verify the complete automated deployment flow

## Notes

- Web search results and LLM parsing are inherently non-deterministic —
  re-running the same query may surface different articles.
- The pipeline stops early (rather than producing a thin document) if fewer
  than 3 articles pass the filter stage for a given topic.
