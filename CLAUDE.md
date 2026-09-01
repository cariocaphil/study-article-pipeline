# Study Article Collection Doc Generator Pipeline

## What this project does
Given a topic (film, book, author, etc.), a source language, a translation
language, and the user's CEFR level, this pipeline searches for native-language
review articles, extracts vocabulary and expressions above the user's level,
and compiles everything into a printable PDF for language study.

## Stack
- Python 3.11+
- Anthropic Python SDK (claude-sonnet-4-6, web search tool enabled)
- ReportLab (PDF document generation)
- Pydantic (schema validation between agents)
- Pyright (`standard` type checking — config in `pyproject.toml`)
- stdlib `logging` (no `print()` in pipeline code)

## Agents and responsibilities
| Agent       | File                        | Owns |
|-------------|-----------------------------|------|
| Orchestrator | src/orchestrator.py        | Input parsing, agent sequencing, fallback handling |
| Search      | src/agents/search_agent.py  | Find candidate article URLs in the source language |
| Filter      | src/agents/filter_agent.py  | Confirm each URL is a real review, fetch full text + author |
| Extract     | src/agents/extract_agent.py | Pull phrases above user's CEFR level, with translations |
| Review      | src/agents/review_agent.py  | Independently audit extracted phrases for quality, drop low-quality items |
| Compile     | src/agents/compile_agent.py | Produce the final PDF |

## Tools
Validation tools live in `src/tools/`. They are **client-executed**: the agent
implements a tool-use loop (send prompt → handle `tool_use` blocks → run local
Python → return `tool_result` → continue until final response). Only items
that passed tool validation are kept.

| Tool | File | Used by | What it checks |
|------|------|---------|----------------|
| `validate_url_reachable(url)` | `src/tools/validate_url_reachable.py` | `search_agent.py` | URL passes SSRF checks; HTTP HEAD responds 2xx/3xx |
| `verify_quote(sentence, article_text)` | `src/tools/verify_quote.py` | `extract_agent.py` | `sentence_context` is a verbatim quote from the article |
| `validate_translation(phrase, translation)` | `src/tools/validate_translation.py` | `extract_agent.py` | Translation is non-empty and not a lazy copy of the source phrase |
| `validate_topic(topic)` | `src/tools/validate_topic.py` | `orchestrator.py` | Topic is non-empty, within length limits, and safe for filenames/prompts |

`search_agent.py` also uses Anthropic's server-executed `web_search` tool.
`filter_agent.py` uses `web_search` only (no custom tools).

When adding a new client-side tool: define the function in `src/tools/`,
register its schema in the agent, handle `tool_use` in the loop, and filter
the final parsed output to only items the tool marked as valid.

`extract_agent.py` also retries when the model returns prose instead of
parseable JSON: it sends a continuation prompt and re-calls the API (up to 3
parse attempts) before raising. Apply the same pattern if another agent's tool
loop can end with planning text rather than structured output.

Agents that call `client.messages.create()` should call `record_api_usage()`
from `src/utils/observability.py` after each response when a `UsageTracker` is
available (passed from the orchestrator).

### Anthropic API typing

Agent tool loops use typed Anthropic SDK types. Shared helpers live in
`src/utils/anthropic_utils.py`:

| Helper | Use for |
|--------|---------|
| `message_text(response)` | Extract joined text from a `Message` (check `block.type == "text"`) |
| `as_tool_param(schema)` | Cast client-side tool JSON schemas to `ToolParam` |
| `require_str_field(data, field)` | Safely read string fields from `tool_use` block inputs |

Conventions for agents with tool loops:

- Type conversation history as `list[MessageParam]`
- Type tool result payloads as `list[ToolResultBlockParam]`
- In unit tests, mock responses via `tests/anthropic_mocks.mock_message()` so
  `usage` metadata is present (required by `record_api_usage`)

## Schema
Inter-agent data passes through typed models in `src/schemas/`:

| Model | File | Purpose |
|-------|------|---------|
| `Article`, `ExtractedPhrase`, `PipelineOutput`, … | `src/schemas/article.py` | Pydantic models between agents |
| `FilteredArticle` | `src/schemas/article.py` | TypedDict returned by `filter_agent` before `Article` construction |
| `PipelineRunResult` | `src/schemas/pipeline_result.py` | Orchestrator return value (path, run ID, timings, token counts) |

Prefer Pydantic models or TypedDicts over raw `dict` at agent boundaries.
Never pass unstructured strings between agents when a schema exists.

## Observability

`src/utils/observability.py` provides pipeline-wide logging and run metrics:

- `configure_logging()` — called once at pipeline start
- `new_run_id()`, `StageTimer`, `UsageTracker` — per-run ID, stage timing, token totals
- `record_api_usage()` — log Anthropic `Message.usage` after each API call
- `user_facing_pipeline_error()` — map internal exceptions to Streamlit-safe messages

`run_pipeline()` returns `PipelineRunResult` (not a bare path string). The
orchestrator accepts an optional `on_stage` callback for UI progress updates.

Use `logging.getLogger(__name__)` in agents and tools. Validation tools support
`quiet=True` to suppress info logs when called from evals or bulk tests.

## Output
Generated PDF files land in output/
Filename format: {topic}_{source_lang}_{translation_lang}_{level}.pdf

## Slash command
/find-articles "<topic>" <source_language> <translation_language> <cefr_level> [n_articles]
Example: /find-articles "Entroncamento" portuguese german C1 5

## Fallback rule
If fewer than 3 articles pass the filter stage, log a clear warning and stop.
Do not pad the document with low-quality matches.

## Environment
ANTHROPIC_API_KEY in .env — never commit this file.

## Trust boundaries

External content is treated as untrusted data, not instructions:

| Boundary | Mechanism | File |
|----------|-----------|------|
| User topic input | `validate_topic()` rejects empty, oversized, or unsafe strings | `src/tools/validate_topic.py` |
| Outbound URL fetch | `is_safe_fetch_url()` blocks private/local addresses before HTTP HEAD | `src/tools/url_safety.py` |
| Streamlit user topic | `escape_markdown_text()` before embedding topic in confirmation markdown | `src/utils/run_summary.py` |
| Retrieved article text | `wrap_untrusted_content()` + preamble in agent prompts | `src/utils/untrusted_content.py` |

Agents that consume internet-sourced text (`filter_agent`, `extract_agent`, `review_agent`)
use `UNTRUSTED_CONTENT_PREAMBLE` and explicit delimiters. This reduces prompt-injection
risk from malicious article pages but does not eliminate it.

## Development checks

Run before opening a PR:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -m "not slow"
```

CI (`.github/workflows/ci.yml`) runs Ruff, Pyright, fast pytest, and offline
eval smoke tests on pushes and pull requests to `main`.

## Skills
Skills are located in `.claude/skills/`. Claude Code should load them when relevant.

| Skill | File | When to apply |
|---|---|---|
| Document formatter | `.claude/skills/pdf-formatted.md` | Any time the compile agent or document layout is discussed or modified |
| Article filter criteria | `.claude/skills/article-filter-criteria.md` | Already injected at runtime in filter_agent.py |
| CEFR extraction guide | `.claude/skills/cefr-extraction-guide.md` | Already injected at runtime in extract_agent.py |
| Phrase quality reviewer | `.claude/skills/phrase-quality-reviewer.md` | Already injected at runtime in review_agent.py |
| Translation adequacy rubric | `.claude/skills/translation-adequacy-rubric.md` | Already injected at runtime in translation quality judge |

## Evaluations
Deterministic evals live in `evals/`. They score saved pipeline outputs — no
API calls required.

| Evaluator | Input | Metric |
|-----------|-------|--------|
| `quote_faithfulness` | `PipelineOutput` JSON | % of phrases whose `sentence_context` is verbatim in `full_text` |
| `filter_classification` | labeled URL dataset (`.jsonl`) | accuracy, precision, recall, F1 on accept/reject decisions |
| `review_actions` | labeled phrase-list dataset (`.jsonl`) | removal precision/recall/F1 and per-action accuracy |
| `extract_phrase_recall` | gold phrase dataset (`.jsonl`) | phrase recall against human labels |
| `translation_quality` | labeled translation dataset (`.jsonl`) | judge accuracy vs human adequacy labels |
| `search_url_recall` | gold URL dataset (`.jsonl`) | URL recall against stable review links |
| `pipeline_quality` | `PipelineOutput` JSON | composite score: structure, phrase coverage, quotes, translations, level floor |

Run locally:
```bash
uv run python -m evals.runners.run_evals \
  --suite quote_faithfulness \
  --input evals/datasets/fixtures/sample_pipeline_output.json

uv run python -m evals.runners.run_evals \
  --suite filter_classification \
  --input evals/datasets/filter/urls.jsonl \
  --predictions evals/datasets/fixtures/filter_predictions.jsonl

uv run python -m evals.runners.run_evals \
  --suite review_actions \
  --input evals/datasets/review/phrase_lists.jsonl \
  --predictions evals/datasets/fixtures/review_predictions.jsonl

uv run python -m evals.runners.run_evals \
  --suite extract_phrase_recall \
  --input evals/datasets/extract/gold_phrases.jsonl \
  --predictions evals/datasets/fixtures/extract_predictions.jsonl

uv run python -m evals.runners.run_evals \
  --suite translation_quality \
  --input evals/datasets/translation/phrases.jsonl \
  --predictions evals/datasets/fixtures/translation_judge_predictions.jsonl

uv run python -m evals.runners.run_evals \
  --suite search_url_recall \
  --input evals/datasets/search/gold_urls.jsonl \
  --predictions evals/datasets/fixtures/search_predictions.jsonl

uv run python -m evals.runners.run_evals \
  --suite pipeline_quality \
  --input evals/datasets/fixtures/sample_pipeline_output.json
```

Use `--live` with `filter_classification`, `review_actions`,
`extract_phrase_recall`, `translation_quality`, or `search_url_recall` to
score the real agents or judge (API key required). Offline scoring uses cached
predictions in `evals/datasets/fixtures/`.

Compare two saved runs:
```bash
uv run python -m evals.runners.compare_runs \
  --baseline evals/results/BASELINE_RUN_ID \
  --candidate evals/results/CANDIDATE_RUN_ID
```

Results are written to `evals/results/{run_id}/` (`report.json`, `scores.json`,
`failures.jsonl`). Fast eval tests live in `tests/test_evals.py`.

Use `--live` with `translation_quality` locally when you want to run the LLM
judge against the labeled dataset (requires `ANTHROPIC_API_KEY`).

When adding a new evaluator: implement `run(...) -> EvalResult` in
`evals/evaluators/`, register it in `evals/runners/run_evals.py`, add a fixture
or dataset case, and cover it in `tests/test_evals.py`.
