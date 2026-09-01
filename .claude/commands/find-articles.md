# find-articles

Run the Study Article Collection Doc Generator Pipeline.

## Usage
/find-articles "<topic>" <source_language> <translation_language> <cefr_level> [topic_type] [n_articles]

## Examples
/find-articles "Entroncamento" portuguese german C1 5
/find-articles "Amadeus" english german C1 theatre 5
/find-articles "O Crime do Padre Amaro" portuguese french B2 book 3
/find-articles "Pedro Páramo" spanish english C1 4

## What this does
1. Searches for native-language review articles about the topic
2. Filters each URL to confirm it is a genuine review and extracts full text
3. Extracts vocabulary and expressions at or above the specified CEFR level
4. Compiles everything into a printable PDF in the output/ folder

## Run
```bash
uv run python -m src.orchestrator "$TOPIC" "$SOURCE_LANGUAGE" "$TRANSLATION_LANGUAGE" "$CEFR_LEVEL" "$TOPIC_TYPE" "$N_ARTICLES"
```