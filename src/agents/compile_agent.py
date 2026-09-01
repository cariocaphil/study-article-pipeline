"""
Compile agent.
Takes a validated PipelineOutput and produces a printable PDF file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from src.schemas.article import PipelineOutput

logger = logging.getLogger(__name__)

_FONT_NAME = "StudyDocUnicode"
_FONT_REGISTERED = False


def _register_unicode_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return

    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / "src" / "assets" / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for font_path in candidates:
        if font_path.is_file():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
            _FONT_REGISTERED = True
            return

    raise RuntimeError(
        "No Unicode font found for PDF generation. "
        "Install DejaVu Sans or place DejaVuSans.ttf in src/assets/fonts/."
    )


def _styles() -> dict[str, ParagraphStyle]:
    _register_unicode_font()
    return {
        "title": ParagraphStyle(
            "Title",
            fontName=_FONT_NAME,
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName=_FONT_NAME,
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "heading2": ParagraphStyle(
            "Heading2",
            fontName=_FONT_NAME,
            fontSize=14,
            leading=18,
            spaceBefore=6,
            spaceAfter=6,
        ),
        "heading3": ParagraphStyle(
            "Heading3",
            fontName=_FONT_NAME,
            fontSize=12,
            leading=16,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName=_FONT_NAME,
            fontSize=11,
            leading=11 * 1.3,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontName=_FONT_NAME,
            fontSize=11,
            leading=11 * 1.3,
            leftIndent=12,
            bulletIndent=0,
            spaceAfter=2,
        ),
        "context": ParagraphStyle(
            "Context",
            fontName=_FONT_NAME,
            fontSize=11,
            leading=11 * 1.3,
            leftIndent=12 + cm,
            spaceAfter=8,
        ),
    }


def _bold_label(label: str, value: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f"<b>{escape(label)}</b>{escape(value)}", style)


def compile_document(output: PipelineOutput, output_path: str) -> str:
    """
    Generates a PDF file from a PipelineOutput.
    Returns the path to the generated file.
    """

    styles = _styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=4.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f'Study Article Collection regarding "{output.topic}"',
    )

    story: list[Flowable] = []

    story.append(
        Paragraph(
            f'Study Article Collection regarding "{escape(output.topic)}"',
            styles["title"],
        )
    )
    story.append(
        Paragraph(
            (
                f"<i>Source language: {escape(output.source_language.capitalize())}  |  "
                f"Translations: {escape(output.translation_language.capitalize())}  |  "
                f"Level: {escape(output.user_level.value)}</i>"
            ),
            styles["meta"],
        )
    )
    story.append(Spacer(1, 6))

    for i, article in enumerate(output.articles, start=1):
        story.append(Paragraph(f"Article {i}", styles["heading2"]))
        story.append(_bold_label("Title: ", article.title, styles["body"]))
        author = article.author if article.author else "Unknown"
        story.append(_bold_label("Author: ", author, styles["body"]))
        story.append(_bold_label("Source: ", article.source_name, styles["body"]))
        story.append(_bold_label("Link: ", article.url, styles["body"]))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Article Text", styles["heading3"]))
        for paragraph in article.full_text.split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                story.append(Paragraph(escape(paragraph), styles["body"]))

        story.append(Spacer(1, 6))
        story.append(Paragraph("Vocabulary &amp; Expressions", styles["heading3"]))

        if not article.phrases:
            story.append(
                Paragraph(
                    "No phrases extracted above the specified level.",
                    styles["body"],
                )
            )
        else:
            for phrase in article.phrases:
                story.append(
                    Paragraph(
                        (
                            f"<bullet>&bull;</bullet> "
                            f"<b>[{escape(phrase.category.value)}] "
                            f"[{escape(phrase.estimated_level.value)}] "
                            f"{escape(phrase.phrase)}</b> "
                            f"&mdash; {escape(phrase.translation)}"
                        ),
                        styles["bullet"],
                    )
                )
                story.append(
                    Paragraph(
                        f'<i>"{escape(phrase.sentence_context)}"</i>',
                        styles["context"],
                    )
                )

        if i < len(output.articles):
            story.append(PageBreak())

    doc.build(story)
    logger.info("Document saved to %s", output_path)
    return output_path


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from src.schemas.article import Article, CEFRLevel, ExtractedPhrase, PhraseCategory

    sample = PipelineOutput(
        topic="Entroncamento",
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        articles=[
            Article(
                title="Entroncamento, a Crítica | Pedro Cabeleira revela a sensibilidade na violência",
                author="Matilde Sousa",
                url="https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/",
                source_name="magazine-hd.com",
                full_text=(
                    "Em «Entroncamento» acompanhamos Laura, que foge de um passado turbulento, "
                    "refugiando-se nesta cidade do distrito de Santarém para recomeçar a sua vida. "
                    "Contudo, apesar de tentar encontrar um emprego honesto e uma vida melhor, "
                    "começa a entrar em pequenos esquemas e crimes, motivados por familiares e "
                    "conhecidos que a envolvem numa teia de cumplicidades difícil de escapar."
                ),
                phrases=[
                    ExtractedPhrase(
                        phrase="entrar em pequenos esquemas",
                        sentence_context="começa a entrar em pequenos esquemas e crimes, motivados por familiares e conhecidos",
                        translation="in kleine Machenschaften verwickelt werden",
                        category=PhraseCategory.idiom,
                        estimated_level=CEFRLevel.C1,
                    ),
                    ExtractedPhrase(
                        phrase="teia de cumplicidades",
                        sentence_context="que a envolvem numa teia de cumplicidades difícil de escapar",
                        translation="Netz der Komplizenschaft",
                        category=PhraseCategory.idiom,
                        estimated_level=CEFRLevel.C1,
                    ),
                ],
            )
        ],
    )

    compile_document(sample, "output/test_output.pdf")
