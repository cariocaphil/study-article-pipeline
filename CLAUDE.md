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
| Compile     | src/agents/compile_agent.py | Produce the final .docx |

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
| Document formatter | `.claude/skills/docx-formatter.md` | Any time the compile agent or document layout is discussed or modified |
| Article filter criteria | `.claude/skills/article-filter-criteria.md` | Already injected at runtime in filter_agent.py |
| CEFR extraction guide | `.claude/skills/cefr-extraction-guide.md` | Already injected at runtime in extract_agent.py |