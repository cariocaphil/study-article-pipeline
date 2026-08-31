import os

import streamlit as st

from src.orchestrator import run_pipeline
from src.tools.validate_topic import topic_validation_error

st.set_page_config(
    page_title="Study Article Collection",
    page_icon="📚",
    layout="centered",
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
    placeholder='e.g. "Entroncamento", "Romería", "O riso e a faca"',
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

# ── Run ───────────────────────────────────────────────────────────────────────
if st.button("Generate study document", type="primary", use_container_width=True):
    topic_error = topic_validation_error(topic)
    if topic_error:
        st.error(topic_error)
    else:
        with st.spinner("Running pipeline — this takes 2-3 minutes..."):
            log_output = st.empty()
            try:
                output_path = run_pipeline(
                    topic=topic.strip(),
                    source_language=source_language,
                    translation_language=translation_language,
                    user_level=user_level,
                    n_articles=n_articles,
                )
                st.success("Document generated successfully.")

                # ── Download button ───────────────────────────────────────────
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Download your study document",
                        data=f,
                        file_name=os.path.basename(output_path),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )

            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Something went wrong: {e}")
