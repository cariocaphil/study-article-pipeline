# Study Article Collection Doc Generator Pipeline

Given a topic (film, book, author, etc.), a source language, a translation
language, and your CEFR level, this pipeline searches the web for
native-language review articles, extracts vocabulary and expressions above
your level (with translations), and compiles everything into a printable
Word document for language study.

## How it works

Four agents run in sequence, each owning one stage of the pipeline:

| Stage | Agent | File | Responsibility |
|-------|-------|------|-----------------|
| 1 | Search | `src/agents/search_agent.py` | Find candidate article URLs written in the source language |
| 2 | Filter | `src/agents/filter_agent.py` | Confirm each URL is a genuine review, fetch full text + author |
| 3 | Extract | `src/agents/extract_agent.py` | Pull vocabulary/constructions/idioms at or above your CEFR level, with translations |
| 4 | Compile | `src/agents/compile_agent.py` | Produce the final `.docx` |

`src/orchestrator.py` wires these together, handles CLI input, and enforces
the fallback rule: if fewer than 3 articles pass the filter stage, the
pipeline stops with a warning instead of padding the document with
low-quality matches.

All data passed between agents is validated through Pydantic models in
`src/schemas/article.py` (`Article`, `ExtractedPhrase`, `PipelineOutput`).

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

Run the test suite with:

```bash
uv run pytest
```

## Project structure

```
app.py                        # Streamlit web UI entry point
.claude/
├── commands/
│   └── find-articles.md      # slash command definition
└── hooks/
    └── post-run.sh           # opens latest .docx after CLI pipeline run
src/
├── orchestrator.py           # wires agents together, CLI entry point
├── agents/
│   ├── search_agent.py       # finds candidate article URLs
│   ├── filter_agent.py       # validates + fetches article content
│   ├── extract_agent.py      # extracts phrases above CEFR level
│   └── compile_agent.py      # generates the .docx
├── schemas/
│   └── article.py            # Pydantic models shared between agents
└── utils/
    └── json_utils.py         # robust JSON extraction from LLM responses
tests/
├── test_app.py               # Streamlit UI tests (AppTest)
└── test_json_utils.py        # JSON repair/parsing tests
output/                        # generated .docx files land here
```

## Notes

- Web search results and LLM parsing are inherently non-deterministic —
  re-running the same query may surface different articles.
- The pipeline stops early (rather than producing a thin document) if fewer
  than 3 articles pass the filter stage for a given topic.
