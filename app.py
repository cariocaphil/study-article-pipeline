import logging
import os

import streamlit as st

from src.orchestrator import run_pipeline
from src.schemas.article import TopicType
from src.schemas.pipeline_result import PipelineRunResult
from src.tools.validate_topic import topic_validation_error
from src.utils.aca_identity import (
    get_authenticated_user,
    identity_provider_label,
    identity_required,
    login_url,
    logout_url,
)
from src.utils.observability import STAGE_LABELS, user_facing_pipeline_error
from src.utils.quota import (
    QuotaExceededError,
    QuotaUnavailableError,
    consume_generation,
    get_remaining,
    quota_enabled,
)
from src.utils.run_summary import format_post_run_summary, format_run_summary

logger = logging.getLogger(__name__)

APP_TITLE = "📚 Study Article Collection Generator."
PAGE_TITLE = "Study Article Collection Generator"
DEFAULT_N_ARTICLES = 3

TOPIC_TYPE_OPTIONS = {
    "Film": TopicType.film,
    "Series": TopicType.series,
    "Book": TopicType.book,
    "Theatre production": TopicType.theatre,
    "Album": TopicType.album,
}

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon="📚",
    layout="centered",
)

if "awaiting_confirmation" not in st.session_state:
    st.session_state.awaiting_confirmation = False
if "last_run_result" not in st.session_state:
    st.session_state.last_run_result = None
if "inputs_locked" not in st.session_state:
    st.session_state.inputs_locked = False
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False
if "display_error" not in st.session_state:
    st.session_state.display_error = None


def _render_login_landing() -> None:
    st.title(APP_TITLE)
    st.markdown("**Prepare for language lessons through real-world reading.**")
    st.markdown(
        "Sign in to create printable study documents from authentic native-language articles."
    )
    st.link_button(
        "Sign in with Microsoft",
        url=login_url("aad"),
        use_container_width=True,
    )
    st.link_button(
        "Sign in with Google",
        url=login_url("google"),
        use_container_width=True,
    )


authenticated_user = get_authenticated_user()
if identity_required() and authenticated_user is None:
    _render_login_landing()
    st.stop()

if authenticated_user is not None and quota_enabled():
    remaining = get_remaining(authenticated_user.user_id)
    provider_label = identity_provider_label(authenticated_user.identity_provider)
    provider_suffix = f" via {provider_label}" if provider_label else ""
    st.caption(
        f"Signed in as {authenticated_user.display_name}{provider_suffix} · "
        f"{remaining} generation(s) left today (UTC). "
        f"[Sign out]({logout_url()})"
    )


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


def _run_confirmed_pipeline(
    *,
    stripped_topic: str,
    source_language: str,
    translation_language: str,
    user_level: str,
    n_articles: int,
    topic_type: TopicType,
) -> None:
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
                topic_type=topic_type,
                on_stage=on_stage,
            )
            status.update(label="Pipeline complete", state="complete", expanded=False)
            st.session_state.awaiting_confirmation = False
            st.session_state.pending_run_config = None
            st.session_state.last_run_result = result

        except ValueError as e:
            status.update(label="Pipeline failed", state="error", expanded=False)
            st.session_state.display_error = user_facing_pipeline_error(e)
        except Exception as e:
            status.update(label="Pipeline failed", state="error", expanded=False)
            logger.exception("Unexpected pipeline error")
            st.session_state.display_error = user_facing_pipeline_error(e)


st.title(APP_TITLE)
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

inputs_locked = st.session_state.inputs_locked
pipeline_running = st.session_state.pipeline_running

if st.session_state.display_error:
    st.error(st.session_state.display_error)
    st.session_state.display_error = None

# ── Inputs ────────────────────────────────────────────────────────────────────
topic = st.text_input(
    "Topic",
    placeholder='e.g. "Entroncamento", "Amadeus", "Madre (2017)"',
    help=(
        "Include a release or publication year when it helps disambiguate films or books "
        "(for example, Madre (2017)). The year is optional."
    ),
    disabled=inputs_locked,
)

topic_type = st.selectbox(
    "Topic type",
    list(TOPIC_TYPE_OPTIONS.keys()),
    disabled=inputs_locked,
)

col1, col2 = st.columns(2)

with col1:
    source_language = st.selectbox(
        "Source language",
        ["portuguese", "spanish", "catalan", "french", "italian", "german"],
        disabled=inputs_locked,
    )

with col2:
    translation_language = st.selectbox(
        "Translation language",
        ["german", "english", "french", "spanish", "portuguese", "italian"],
        disabled=inputs_locked,
    )

col3, col4 = st.columns(2)

with col3:
    user_level = st.selectbox(
        "Your CEFR level",
        ["A1", "A2", "B1", "B2", "C1", "C2"],
        index=4,  # default to C1
        disabled=inputs_locked,
    )

with col4:
    n_articles = st.slider(
        "Number of articles",
        min_value=3,
        max_value=8,
        value=DEFAULT_N_ARTICLES,
        disabled=inputs_locked,
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

pending_run_config = st.session_state.get("pending_run_config")
if st.session_state.inputs_locked and pending_run_config is not None:
    (
        stripped_topic,
        topic_type,
        source_language,
        translation_language,
        user_level,
        n_articles,
    ) = pending_run_config
    topic_error = None
elif pending_run_config != run_config:
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
    if authenticated_user is not None and quota_enabled():
        remaining = get_remaining(authenticated_user.user_id)
        st.info(f"{remaining} generation(s) remaining today (UTC).")

    confirm_col, back_col = st.columns(2)
    with confirm_col:
        confirm_clicked = st.button(
            "Confirm & generate",
            type="primary",
            use_container_width=True,
            disabled=pipeline_running,
        )
    with back_col:
        back_clicked = st.button(
            "Go back",
            use_container_width=True,
            disabled=pipeline_running,
        )

    if back_clicked:
        st.session_state.awaiting_confirmation = False
        st.session_state.pending_run_config = None
        st.session_state.inputs_locked = False
        st.rerun()

    if confirm_clicked:
        st.session_state.pipeline_running = True
        st.session_state.last_run_result = None
        st.session_state.display_error = None

        if authenticated_user is not None and quota_enabled():
            try:
                consume_generation(authenticated_user.user_id)
            except QuotaExceededError:
                st.session_state.display_error = (
                    "Daily generation limit reached. Try again tomorrow (UTC)."
                )
            except QuotaUnavailableError:
                st.session_state.display_error = (
                    "Could not verify your daily quota. Please try again in a moment."
                )
            else:
                _run_confirmed_pipeline(
                    stripped_topic=stripped_topic,
                    source_language=source_language,
                    translation_language=translation_language,
                    user_level=user_level,
                    n_articles=n_articles,
                    topic_type=TOPIC_TYPE_OPTIONS[topic_type],
                )
        else:
            _run_confirmed_pipeline(
                stripped_topic=stripped_topic,
                source_language=source_language,
                translation_language=translation_language,
                user_level=user_level,
                n_articles=n_articles,
                topic_type=TOPIC_TYPE_OPTIONS[topic_type],
            )

        st.session_state.pipeline_running = False
        st.session_state.inputs_locked = False
        st.rerun()
else:
    if st.button(
        "Generate study document",
        type="primary",
        use_container_width=True,
        disabled=inputs_locked,
    ):
        if topic_error:
            st.error(topic_error)
        else:
            st.session_state.awaiting_confirmation = True
            st.session_state.pending_run_config = run_config
            st.session_state.inputs_locked = True
            st.rerun()

if st.session_state.last_run_result is not None:
    last_result = st.session_state.last_run_result
    st.success("Document generated successfully.")
    st.markdown(format_post_run_summary(last_result))
    _render_generated_document(last_result)
