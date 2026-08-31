"""
Tests for src/agents/compile_agent.py.

No Anthropic API calls are made here — compile_document() is a pure
docx-generation step — so these run fast and unmarked.
"""

import os

from docx import Document

from src.agents.compile_agent import compile_document
from src.schemas.article import (
    Article,
    CEFRLevel,
    ExtractedPhrase,
    PhraseCategory,
    PipelineOutput,
)


def _sample_pipeline_output() -> PipelineOutput:
    return PipelineOutput(
        topic="Entroncamento",
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        articles=[
            Article(
                title="Entroncamento, a Crítica",
                author="Matilde Sousa",
                url="https://example.com/entroncamento-review",
                source_name="example.com",
                full_text=(
                    "Em Entroncamento acompanhamos Laura, que foge de um passado turbulento."
                ),
                phrases=[
                    ExtractedPhrase(
                        phrase="entrar em pequenos esquemas",
                        sentence_context=("começa a entrar em pequenos esquemas e crimes"),
                        translation="in kleine Machenschaften verwickelt werden",
                        category=PhraseCategory.idiom,
                        estimated_level=CEFRLevel.C1,
                    ),
                ],
            )
        ],
    )


def test_compile_creates_docx(temp_output_dir):
    output_path = os.path.join(temp_output_dir, "test_output.docx")

    result_path = compile_document(_sample_pipeline_output(), output_path)

    assert result_path == output_path
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_compile_contains_article_text(temp_output_dir):
    output_path = os.path.join(temp_output_dir, "test_output.docx")
    pipeline_output = _sample_pipeline_output()

    compile_document(pipeline_output, output_path)

    doc = Document(output_path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    article = pipeline_output.articles[0]
    assert article.title in full_text
    assert "Laura" in full_text
    assert article.phrases[0].phrase in full_text
    assert article.phrases[0].translation in full_text
