# Phrase Quality Reviewer

## Purpose
Review an extracted phrase list from a language study article and flag items
that don't meet quality criteria. Apply this after the extract agent runs,
before compiling the final document.

## Quality criteria

### Flag as REMOVE
- Proper nouns: names of people, films, cities, publications (e.g. "Pedro Cabeleira",
  "Entroncamento", "Cannes")
- Phrases that are just the topic itself or its derivatives
- Single letters or punctuation fragments
- Phrases under 2 characters

### Flag as REVIEW
- Near-duplicates: two phrases that express the same concept
  (e.g. "comunidades marginalizadas" and "marginalização" in the same list)
- Items whose estimated_level seems too low for the stated user level
  (e.g. a phrase labelled B2 in a C1 user's list — the floor filter should
  have caught this but occasionally doesn't)
- English or French words used as loanwords that the user likely already knows
  (e.g. "gangsta", "low cost", "au jour le jour" for a German speaker)

### Keep
- Idiomatic expressions unique to the source language
- Constructions that don't translate word-for-word
- Vocabulary with strong register specificity (film criticism, legal, literary)
- Phrases the user is unlikely to encounter in standard language learning materials

## Output format
Return a JSON array where each item has:
- phrase: the original phrase
- action: "keep" | "review" | "remove"
- reason: one short sentence explaining the decision

## Usage
Load this skill when asked to review or audit a phrase list before document
compilation. Do not apply it automatically — only when explicitly invoked.