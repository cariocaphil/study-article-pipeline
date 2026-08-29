import streamlit as st
import os
from src.orchestrator import run_pipeline

st.set_page_config(
    page_title="Study Article Collection Doc Generator",
    page_icon="📚",
    layout="centered",
)

st.title("📚 Study Article Collection Doc Generator")
st.markdown("Find native-language review articles and generate a printable study document.")

st.divider()

# ── Inputs ────────────────────────────────────────────────────────────────────
topic = st.text_input(
    "Topic",
    placeholder='e.g. "Entroncamento", "Pedro Páramo", "Saramago"',
)

col1, col2 = st.columns(2)

with col1:
    source_language = st.selectbox(
        "Source language",
        ["portuguese", "spanish", "french", "italian", "german"],
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
    if not topic.strip():
        st.error("Please enter a topic.")
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
                st.success(f"Document generated successfully.")

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