# Document Formatter

## Purpose
Define formatting preferences for the generated study document.
Apply these when the compile agent builds the PDF.

## Page layout
- Paper size: A4
- Left margin: 3cm (for binding)
- Right margin: 4.5cm (wide — for hand annotation)
- Top margin: 2.5cm
- Bottom margin: 2.5cm

## Typography
- Body text: 11pt, 1.3 line spacing (readable but compact for printing)
- Article heading (Article 1, Article 2...): Heading 2 style
- Section labels (Article Text, Vocabulary & Expressions): Heading 3 style
- Metadata lines (Title, Author, Source, Link): bold label, normal value

## Phrase list
- Format: bullet list
- Each phrase on one line: [category] [level] phrase — translation
- Sentence context on the next line, indented 1cm, italic
- Leave one empty line between phrases for hand-annotation space

## Page breaks
- One page break between articles
- No page break between Article Text and Vocabulary & Expressions

## Footer
- On every page: document title left-aligned, page number right-aligned
- Footer text: 9pt, same Unicode font as body text
- Title format: `Study Article Collection regarding "{topic}"`
- Truncate long titles with an ellipsis so they do not overlap the page number
- No header in v1

## General
- No table of contents in v1
