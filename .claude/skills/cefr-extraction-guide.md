# CEFR Extraction Guide for Portuguese

## Purpose
A rubric for estimating CEFR levels when extracting phrases from Portuguese
articles. Apply this when the extract agent assigns estimated_level to phrases.

## Level indicators

### B2
- Common connectors used in formal writing: "contudo", "todavia", "porém"
- Reflexive constructions: "refugiando-se", "debruçando-se"
- Common abstract nouns: "desigualdade", "marginalização"
- Standard film vocabulary: "realizador", "longa-metragem", "argumento"

### C1
- Register-specific vocabulary: "cineastas", "cinematografia", "deveras"
- Fixed expressions not deducible word-for-word: "trilhar um caminho",
  "entrar em esquemas", "dar visibilidade a"
- Nominalizations: "o indizível", "o não-dito", "o devir"
- Constructions with subjunctive in embedded clauses
- Compound nouns specific to a domain: "cidade-dormitório",
  "eleições autárquicas", "direção fotográfica"

### C2
- Rare or literary vocabulary: "chispava", "mortalha", "bravata"
- Philosophical or technical terms used in cultural criticism: "devir",
  "tessitura", "opacidade"
- Highly idiomatic expressions: "pelo na venta", "au jour le jour"
- Archaic or regional forms uncommon in standard European Portuguese

## Notes
- When in doubt between two levels, assign the higher one — the floor
  filter will remove anything below the user's level anyway
- Loanwords from English or French that exist in Portuguese dictionaries
  count as Portuguese vocabulary (e.g. "gangsta", "low cost") but flag
  them as REVIEW in the phrase quality step since the user may already
  know them from their native language