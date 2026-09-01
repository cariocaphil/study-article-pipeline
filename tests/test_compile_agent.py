"""
Tests for src/agents/compile_agent.py.

No Anthropic API calls are made here — compile_document() is a pure
PDF-generation step — so these run fast and unmarked.
"""

import os

import pytest
from pypdf import PdfReader

from src.agents.compile_agent import _document_title, compile_document
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


def _pdf_text(output_path: str) -> str:
    reader = PdfReader(output_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _pdf_page_texts(output_path: str) -> list[str]:
    reader = PdfReader(output_path)
    return [page.extract_text() or "" for page in reader.pages]


def _long_article_text(*, paragraphs: int = 60) -> str:
    paragraph = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
        "tempor incididunt ut labore et dolore magna aliqua."
    )
    return "\n\n".join(paragraph for _ in range(paragraphs))


def _multi_page_pipeline_output() -> PipelineOutput:
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
                full_text=_long_article_text(),
                phrases=[],
            )
        ],
    )


@pytest.fixture
def compiled_pdf(temp_output_dir):
    output_path = os.path.join(temp_output_dir, "test_output.pdf")
    compile_document(_sample_pipeline_output(), output_path)
    return output_path, _sample_pipeline_output()


def test_compile_creates_pdf(compiled_pdf):
    output_path, _ = compiled_pdf

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
    with open(output_path, "rb") as pdf_file:
        assert pdf_file.read(4) == b"%PDF"


def test_compile_contains_article_text(compiled_pdf):
    output_path, pipeline_output = compiled_pdf
    full_text = " ".join(_pdf_text(output_path).split())

    article = pipeline_output.articles[0]
    assert article.title in full_text
    assert "Laura" in full_text
    assert article.phrases[0].phrase in full_text
    assert article.phrases[0].translation in full_text


def test_compile_footer_shows_document_title_on_each_page(compiled_pdf):
    output_path, pipeline_output = compiled_pdf
    expected_title = _document_title(pipeline_output.topic)

    for page_text in _pdf_page_texts(output_path):
        assert expected_title in page_text


def test_compile_footer_shows_page_number_on_each_page(temp_output_dir):
    output_path = os.path.join(temp_output_dir, "multi_page.pdf")
    compile_document(_multi_page_pipeline_output(), output_path)

    page_texts = _pdf_page_texts(output_path)
    assert len(page_texts) >= 2

    for page_number, page_text in enumerate(page_texts, start=1):
        assert _document_title("Entroncamento") in page_text
        assert str(page_number) in page_text


def test_compile_footer_truncates_very_long_topic(temp_output_dir):
    long_topic = "A" * 200
    pipeline = PipelineOutput(
        topic=long_topic,
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        articles=[
            Article(
                title="Short title",
                author="Author",
                url="https://example.com/review",
                source_name="example.com",
                full_text="Short article body without digits.",
                phrases=[],
            )
        ],
    )
    output_path = os.path.join(temp_output_dir, "long_topic_footer.pdf")
    compile_document(pipeline, output_path)

    page_text = _pdf_page_texts(output_path)[0]
    assert "…" in page_text
    assert long_topic not in page_text
