"""
Tests for app.py (the Streamlit web UI).

Uses Streamlit's official AppTest framework to run the script in-process
and inspect the resulting widget tree, without spinning up a real server
or making live Anthropic API calls (src.orchestrator.run_pipeline is
mocked in every scenario that would otherwise trigger it).
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from src.schemas.article import TopicType

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def app():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    return at


class TestAppLayout:
    def test_loads_without_exceptions(self, app):
        assert not app.exception

    def test_title(self, app):
        assert app.title[0].value == "📚 Study Article Collection"

    def test_intro_copy_present(self, app):
        body = " ".join(m.value for m in app.markdown)
        assert "Prepare for language lessons through real-world reading." in body
        assert (
            "Choose a topic, select the language you're learning and your "
            "preferred translation language" in body
        )
        assert "Key vocabulary with translations" in body
        assert "Useful idioms and expressions" in body
        assert "Notable grammatical constructions and sentence patterns" in body
        assert "appear directly after the article they come from" in body
        assert "come to your language lesson with both ideas" in body

    def test_input_widgets_present_with_expected_defaults(self, app):
        assert app.text_input[0].label == "Topic"
        assert app.text_input[0].value == ""

        topic_type, source_language, translation_language, user_level = (
            app.selectbox[0],
            app.selectbox[1],
            app.selectbox[2],
            app.selectbox[3],
        )
        assert topic_type.label == "Topic type"
        assert topic_type.value == "Film"
        assert source_language.label == "Source language"
        assert source_language.value == "portuguese"
        assert translation_language.label == "Translation language"
        assert translation_language.value == "german"
        assert user_level.label == "Your CEFR level"
        assert user_level.value == "C1"

        assert app.slider[0].label == "Number of articles"
        assert app.slider[0].value == 5

        assert app.button[0].label == "Generate study document"


class TestGenerateButton:
    def test_blank_topic_shows_error_without_running_pipeline(self, app):
        with patch("src.orchestrator.run_pipeline") as mock_run:
            app.button[0].click().run(timeout=30)

        mock_run.assert_not_called()
        assert [e.value for e in app.error] == ["Please enter a topic."]

    def test_whitespace_only_topic_shows_error(self, app):
        app.text_input[0].input("   ")
        with patch("src.orchestrator.run_pipeline") as mock_run:
            app.button[0].click().run(timeout=30)

        mock_run.assert_not_called()
        assert [e.value for e in app.error] == ["Please enter a topic."]

    def test_unsafe_topic_shows_error_without_running_pipeline(self, app):
        app.text_input[0].input("Entroncamento/Film")
        with patch("src.orchestrator.run_pipeline") as mock_run:
            app.button[0].click().run(timeout=30)

        mock_run.assert_not_called()
        assert [e.value for e in app.error] == ["Topic contains characters that are not allowed."]

    def test_successful_run_shows_success_and_download_button(self, app):
        app.text_input[0].input("Entroncamento")

        fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"fake docx bytes")

            with patch("src.orchestrator.run_pipeline", return_value=tmp_path) as mock_run:
                app.button[0].click().run(timeout=30)

            mock_run.assert_called_once_with(
                topic="Entroncamento",
                source_language="portuguese",
                translation_language="german",
                user_level="C1",
                n_articles=5,
                topic_type=TopicType.film,
            )
            assert not app.exception
            assert [s.value for s in app.success] == ["Document generated successfully."]
            assert len(app.download_button) == 1
            assert app.download_button[0].label == "⬇️ Download your study document"
        finally:
            os.remove(tmp_path)

    def test_selected_topic_type_is_passed_to_pipeline(self, app):
        app.text_input[0].input("Amadeus")
        app.selectbox[0].select("Theatre production")

        fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"fake docx bytes")

            with patch("src.orchestrator.run_pipeline", return_value=tmp_path) as mock_run:
                app.button[0].click().run(timeout=30)

            assert mock_run.call_args.kwargs["topic_type"] == TopicType.theatre
        finally:
            os.remove(tmp_path)

    def test_value_error_from_pipeline_shown_as_error(self, app):
        app.text_input[0].input("Entroncamento")

        message = "Pipeline stopped: only 1 article(s) passed the filter."
        with patch("src.orchestrator.run_pipeline", side_effect=ValueError(message)):
            app.button[0].click().run(timeout=30)

        assert not app.exception
        assert [e.value for e in app.error] == [message]

    def test_unexpected_error_from_pipeline_shown_with_prefix(self, app):
        app.text_input[0].input("Entroncamento")

        with patch("src.orchestrator.run_pipeline", side_effect=RuntimeError("boom")):
            app.button[0].click().run(timeout=30)

        assert not app.exception
        assert [e.value for e in app.error] == ["Something went wrong: boom"]

    def test_topic_is_stripped_before_being_passed_to_pipeline(self, app):
        app.text_input[0].input("  Entroncamento  ")

        fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"fake docx bytes")

            with patch("src.orchestrator.run_pipeline", return_value=tmp_path) as mock_run:
                app.button[0].click().run(timeout=30)

            assert mock_run.call_args.kwargs["topic"] == "Entroncamento"
        finally:
            os.remove(tmp_path)
