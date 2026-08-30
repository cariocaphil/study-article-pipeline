# Study Article Collection Doc Generator Pipeline

## What this project does
Given a topic (film, book, author, etc.), a source language, a translation
language, and the user's CEFR level, this pipeline searches for native-language
review articles, extracts vocabulary and expressions above the user's level,
and compiles everything into a printable Word document for language study.

## Stack
- Python 3.11+
- Anthropic Python SDK (claude-sonnet-4-6, web search tool enabled)
- python-docx (Word document generation)
- Pydantic (schema validation between agents)

## Agents and responsibilities
| Agent       | File                        | Owns |
|-------------|-----------------------------|------|
| Orchestrator | src/orchestrator.py        | Input parsing, agent sequencing, fallback handling |
| Search      | src/agents/search_agent.py  | Find candidate article URLs in the source language |
| Filter      | src/agents/filter_agent.py  | Confirm each URL is a real review, fetch full text + author |
| Extract     | src/agents/extract_agent.py | Pull phrases above user's CEFR level, with translations |
| Review      | src/agents/review_agent.py  | Independently audit extracted phrases for quality, drop low-quality items |
| Compile     | src/agents/compile_agent.py | Produce the final .docx |

## Tools
Validation tools live in `src/tools/`. They are **client-executed**: the agent
implements a tool-use loop (send prompt → handle `tool_use` blocks → run local
Python → return `tool_result` → continue until final response). Only items
that passed tool validation are kept.

| Tool | File | Used by | What it checks |
|------|------|---------|----------------|
| `validate_url_reachable(url)` | `src/tools/validate_url_reachable.py` | `search_agent.py` | HTTP HEAD request; URL responds 2xx/3xx |
| `verify_quote(sentence, article_text)` | `src/tools/verify_quote.py` | `extract_agent.py` | `sentence_context` is a verbatim quote from the article |
| `validate_translation(phrase, translation)` | `src/tools/validate_translation.py` | `extract_agent.py` | Translation is non-empty and not a lazy copy of the source phrase |

`search_agent.py` also uses Anthropic's server-executed `web_search` tool.
`filter_agent.py` uses `web_search` only (no custom tools).

When adding a new client-side tool: define the function in `src/tools/`,
register its schema in the agent, handle `tool_use` in the loop, and filter
the final parsed output to only items the tool marked as valid.

`extract_agent.py` also retries when the model returns prose instead of
parseable JSON: it sends a continuation prompt and re-calls the API (up to 3
parse attempts) before raising. Apply the same pattern if another agent's tool
loop can end with planning text rather than structured output.

## Schema
All inter-agent data passes through Pydantic models in src/schemas/article.py.
Never pass raw strings between agents.

## Output
Generated .docx files land in output/
Filename format: {topic}_{source_lang}_{translation_lang}_{level}.docx

## Slash command
/find-articles "<topic>" <source_language> <translation_language> <cefr_level> [n_articles]
Example: /find-articles "Entroncamento" portuguese german C1 5

## Fallback rule
If fewer than 3 articles pass the filter stage, log a clear warning and stop.
Do not pad the document with low-quality matches.

## Environment
ANTHROPIC_API_KEY in .env — never commit this file.

## Skills
Skills are located in `.claude/skills/`. Claude Code should load them when relevant.

| Skill | File | When to apply |
|---|---|---|
| Document formatter | `.claude/skills/docx-formatted.md` | Any time the compile agent or document layout is discussed or modified |
| Article filter criteria | `.claude/skills/article-filter-criteria.md` | Already injected at runtime in filter_agent.py |
| CEFR extraction guide | `.claude/skills/cefr-extraction-guide.md` | Already injected at runtime in extract_agent.py |
| Phrase quality reviewer | `.claude/skills/phrase-quality-reviewer.md` | Already injected at runtime in review_agent.py |

## Evaluations
Deterministic evals live in `evals/`. They score saved pipeline outputs — no
API calls required.

| Evaluator | Input | Metric |
|-----------|-------|--------|
| `quote_faithfulness` | `PipelineOutput` JSON | % of phrases whose `sentence_context` is verbatim in `full_text` |

Run locally:
```bash
uv run python -m evals.runners.run_evals \
  --suite quote_faithfulness \
  --input evals/datasets/fixtures/sample_pipeline_output.json
```

Results are written to `evals/results/{run_id}/` (`report.json`, `scores.json`,
`failures.jsonl`). Fast eval tests live in `tests/test_evals.py`.

When adding a new evaluator: implement `run(...) -> EvalResult` in
`evals/evaluators/`, register it in `evals/runners/run_evals.py`, add a fixture
or dataset case, and cover it in `tests/test_evals.py`.
