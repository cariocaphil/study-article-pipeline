# CEFR Extraction Guide

## Purpose
A language-agnostic rubric for estimating CEFR levels when extracting phrases
from source-language articles. Apply this when the extract agent assigns
`estimated_level` to phrases. Judge difficulty relative to the article's
source language and domain — not relative to English glosses.

Examples below are illustrative only; prefer the same *kind* of signal in
whatever language you are reading.

## Level indicators

### B2
- Common formal connectors (contrast, cause, concession) that advanced
  learners still mix up or underuse
- Frequent reflexive / pronominal / clitic patterns typical of formal prose
- Abstract nouns common in news and cultural writing (inequality,
  marginalization, representation, and language-equivalent forms)
- Standard domain vocabulary for the topic type (e.g. film: director,
  feature-length film, screenplay — in the source language)

### C1
- Register-specific or specialist vocabulary beyond everyday educated speech
- Fixed expressions and collocations not recoverable word-for-word
- Nominalizations and dense noun phrases typical of criticism or analysis
- Complex embedded clauses (subjunctive, conditional, or equivalent mood /
  modality markers where the language has them)
- Domain compound nouns or multi-word terms that encode cultural or
  institutional concepts

### C2
- Rare, literary, archaic, or strongly regional vocabulary uncommon in
  standard contemporary writing of that language
- Dense philosophical or technical terms used in cultural criticism
- Highly idiomatic expressions that resist literal translation
- Marked stylistic forms (archaic morphology, dialectal spellings, or
  cultivated foreignisms kept untranslated in the source text)

## Notes
- When in doubt between two levels, assign the higher one — the floor
  filter will remove anything below the user's level anyway
- Internationalisms and loanwords that are established in the source
  language still count as source-language vocabulary, but flag them for
  REVIEW in the phrase-quality step when learners may already know them
  from another language they speak
- Do not treat cognates with the user's translation language as
  automatically "easy"; difficulty is about the source-language form and
  usage in context
