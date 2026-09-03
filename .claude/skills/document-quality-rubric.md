# Document Quality Rubric

Use this rubric when judging a complete Study Article Collection document
produced by the pipeline for a given topic, source language, and translation
language.

Score each dimension from **1 (poor)** to **5 (excellent)**. Then set an
**overall** score from 1 to 5 that reflects the document as a whole (not
necessarily a strict arithmetic mean).

## Dimensions

### structure_completeness
- Does the document include enough articles for a useful study pack (typically ≥3)?
- Does each article include title, source, body text, and a non-empty phrase list?
- Is the expected study-document structure present and usable?

### topic_relevance
- Are the articles clearly about the requested topic and content type?
- Would a learner recognize that the collection matches what they asked for?
- Penalize off-topic or wrong-work substitutions.

### article_usefulness
- Are the articles genuine reviews/analyses useful for preparing to discuss the topic?
- Is there enough diversity of voice or angle to support conversation practice?
- Prefer substantive critical writing over thin summaries or near-duplicates.

### phrase_quality
- Are extracted vocabulary, idioms, and constructions useful for a learner at the
  stated CEFR level?
- Is there a healthy mix of categories without padding the list with trivial items?
- Prefer quality and learnability over raw count.

### translation_quality
- Are translations into the requested target language adequate for study?
- Do they convey meaning in context rather than lazy copies of the source?
- Minor stylistic differences are fine if meaning is preserved.

### quote_faithfulness
- Do `sentence_context` quotes appear to come from the accompanying article text?
- Penalize invented, paraphrased, or mismatched contexts.

### duplication
- Are articles and phrases largely distinct rather than repetitive?
- Penalize near-duplicate articles or repeated phrases across the pack.
- A score of 5 means low redundancy; 1 means heavy duplication.

### overall_usefulness
- Would this document help a learner prepare for a language lesson on the topic?
- Consider the pack as a whole: reading material + study phrases + translations.

## Scoring guidance

- Use the full 1–5 scale; reserve 5 for clearly strong documents and 1 for
  clearly unusable ones.
- List concise `defects` for the main problems you noticed (empty list if none).
- Write a short `summary` explaining the overall verdict.
- Be pragmatic: multiple valid article sets can score well; do not require a
  single canonical document.
