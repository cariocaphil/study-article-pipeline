import logging
import os

import streamlit as st

from src.orchestrator import run_pipeline
from src.schemas.article import TopicType
from src.schemas.pipeline_result import PipelineRunResult
from src.tools.validate_topic import topic_validation_error
from src.utils.observability import STAGE_LABELS, user_facing_pipeline_error
from src.utils.run_summary import format_post_run_summary, format_run_summary

logger = logging.getLogger(__name__)

TOPIC_TYPE_OPTIONS = {
    "Film": TopicType.film,
    "Series": TopicType.series,
    "Book": TopicType.book,
    "Theatre production": TopicType.theatre,
    "Album": TopicType.album,
}

st.set_page_config(
    page_title="Study Article Collection",
    page_icon="📚",
    layout="centered",
)

if "awaiting_confirmation" not in st.session_state:
    st.session_state.awaiting_confirmation = False
if "last_run_result" not in st.session_state:
    st.session_state.last_run_result = None


def _render_generated_document(result: PipelineRunResult) -> None:
    if not os.path.exists(result.output_path):
        return

    with open(result.output_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()

    st.pdf(pdf_bytes)
    st.download_button(
        label="⬇️ Download your study document",
        data=pdf_bytes,
        file_name=os.path.basename(result.output_path),
        mime="application/pdf",
        use_container_width=True,
    )

st.title("📚 Study Article Collection")
st.markdown("**Prepare for language lessons through real-world reading.**")

st.markdown(
    "Choose a topic, select the language you're learning and your preferred "
    "translation language, and create a printable study document from "
    "authentic native-language articles."
)

st.markdown(
    "Each article is presented together with its own language-learning "
    "material, extracted directly from the text:"
)

st.markdown(
    "- Key vocabulary with translations\n"
    "- Useful idioms and expressions\n"
    "- Notable grammatical constructions and sentence patterns"
)

st.markdown(
    "The vocabulary, expressions, and constructions appear directly after "
    "the article they come from, so you can learn them in context rather "
    "than as an isolated word list."
)

st.markdown(
    "The goal is simple: read up on a topic, discover how native speakers "
    "talk about it, and come to your language lesson with both ideas and "
    "useful language ready to discuss."
)

st.divider()

# ── Inputs ────────────────────────────────────────────────────────────────────
topic = st.text_input(
    "Topic",
    placeholder='e.g. "Entroncamento", "Amadeus", "Que Horas Ela Volta?"',
)

topic_type = st.selectbox(
    "Topic type",
    list(TOPIC_TYPE_OPTIONS.keys()),
)

col1, col2 = st.columns(2)

with col1:
    source_language = st.selectbox(
        "Source language",
        ["portuguese", "spanish", "catalan", "french", "italian", "german"],
    )

with col2:
    translation_language = st.selectbox(
        "Translation language",
        ["german", "english", "french", "spanish", "portuguese", "italian"],
    )

col3, col4 = st.columns(2)

with col3:
    user_level = st.selectbox(
        "Your CEFR level",
        ["A1", "A2", "B1", "B2", "C1", "C2"],
        index=4,  # default to C1
    )

with col4:
    n_articles = st.slider(
        "Number of articles",
        min_value=3,
        max_value=8,
        value=5,
    )

st.divider()

topic_error = topic_validation_error(topic)
stripped_topic = topic.strip()
run_config = (
    stripped_topic,
    topic_type,
    source_language,
    translation_language,
    user_level,
    n_articles,
)

if st.session_state.get("pending_run_config") != run_config:
    st.session_state.awaiting_confirmation = False

# ── Run ───────────────────────────────────────────────────────────────────────
if st.session_state.awaiting_confirmation and not topic_error:
    st.markdown("### Review your request")
    st.markdown(
        format_run_summary(
            topic=stripped_topic,
            topic_type_label=topic_type,
            source_language=source_language,
            translation_language=translation_language,
            user_level=user_level,
            n_articles=n_articles,
        )
    )

    confirm_col, back_col = st.columns(2)
    with confirm_col:
        confirm_clicked = st.button(
            "Confirm & generate",
            type="primary",
            use_container_width=True,
        )
    with back_col:
        back_clicked = st.button("Go back", use_container_width=True)

    if back_clicked:
        st.session_state.awaiting_confirmation = False
        st.session_state.pending_run_config = None
        st.rerun()

    if confirm_clicked:
        st.session_state.last_run_result = None
        with st.status("Running pipeline…", expanded=True) as status:

            def on_stage(stage: str) -> None:
                status.update(label=STAGE_LABELS.get(stage, stage))

            try:
                result = run_pipeline(
                    topic=stripped_topic,
                    source_language=source_language,
                    translation_language=translation_language,
                    user_level=user_level,
                    n_articles=n_articles,
                    topic_type=TOPIC_TYPE_OPTIONS[topic_type],
                    on_stage=on_stage,
                )
                status.update(label="Pipeline complete", state="complete", expanded=False)
                st.session_state.awaiting_confirmation = False
                st.session_state.pending_run_config = None
                st.session_state.last_run_result = result

            except ValueError as e:
                status.update(label="Pipeline failed", state="error", expanded=False)
                st.error(user_facing_pipeline_error(e))
            except Exception as e:
                status.update(label="Pipeline failed", state="error", expanded=False)
                logger.exception("Unexpected pipeline error")
                st.error(user_facing_pipeline_error(e))
else:
    if st.button("Generate study document", type="primary", use_container_width=True):
        if topic_error:
            st.error(topic_error)
        else:
            st.session_state.awaiting_confirmation = True
            st.session_state.pending_run_config = run_config
            st.rerun()

if st.session_state.last_run_result is not None:
    last_result = st.session_state.last_run_result
    st.success("Document generated successfully.")
    st.markdown(format_post_run_summary(last_result))
    _render_generated_document(last_result)
