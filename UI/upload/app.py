import streamlit as st
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.append(str(ROOT))
# Import your processing function
# Make sure src/pipeline.py contains a function named process_file()
from src.pipeline import process_file


# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="PCOS Canonical Schema Converter",
    layout="centered"
)

# -----------------------------
# Directories
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# -----------------------------
# Custom CSS
# -----------------------------
st.markdown(
    """
    <style>

    .stApp {
        background:
        radial-gradient(circle at 20% 20%, rgba(59,130,246,0.25), transparent 30%),
        radial-gradient(circle at 80% 80%, rgba(139,92,246,0.20), transparent 35%),
        #030712;
        color: white;
    }

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    .block-container {
        max-width: 900px;
        padding-top: 4rem;
    }

    .title {
        text-align: center;
        font-size: 3.2rem;
        font-weight: 800;
        color: white;
        letter-spacing: -1px;
    }

    .subtitle {
        text-align: center;
        color: #94a3b8;
        font-size: 1.2rem;
        margin-bottom: 3rem;
    }

    .glass {
        background: rgba(255,255,255,0.06);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 25px;
        padding: 40px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    }

    .upload-title {
        text-align: center;
        color: white;
        font-size: 1.5rem;
        font-weight: 600;
    }

    .upload-help {
        text-align: center;
        color: #94a3b8;
    }

    .file-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.10);
        padding: 15px;
        border-radius: 15px;
        margin-top: 10px;
        color: white;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Header
# -----------------------------
st.markdown(
    """
    <div class="title">
        PCOS Canonical Schema Converter
    </div>

    <div class="subtitle">
        Standardize clinical datasets into a reproducible canonical schema.
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Upload Card
# -----------------------------
st.markdown(
    """
    <div class="glass">

    <div class="upload-title">
        ☁️ Upload Research Dataset
    </div>

    <br>

    <div class="upload-help">
        Drop XPT, CSV, or Excel files
        <br>
        Supports NHANES-style datasets
    </div>

    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# File Uploader
# -----------------------------
uploaded_files = st.file_uploader(
    "",
    type=["xpt", "csv", "xlsx", "xls"],
    accept_multiple_files=True,
)

# -----------------------------
# Uploaded Files
# -----------------------------
if uploaded_files:

    st.markdown(
        "<h3 style='color:white;'>Uploaded Files</h3>",
        unsafe_allow_html=True,
    )

    for file in uploaded_files:

        size = file.size / 1024

        st.markdown(
            f"""
            <div class="file-card">
                📄 <b>{file.name}</b><br>

                <span style="color:#94a3b8">
                    {size:.1f} KB
                </span>

                <span style="float:right;color:#22c55e">
                    ✓ Ready
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------
    # Analyze Button
    # -----------------------------
    if st.button("Analyze Dataset →", use_container_width=True):

        progress = st.progress(0)

        for index, uploaded_file in enumerate(uploaded_files):

            st.divider()

            st.subheader(f"Processing {uploaded_file.name}")

            # Save uploaded file
            file_path = DATA_DIR / uploaded_file.name

            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            try:
                with st.spinner("Analyzing dataset..."):

                    result = process_file(file_path)

                st.success(f"{uploaded_file.name} processed successfully!")

                # -----------------------------
                # Data Preview
                # -----------------------------
                if "df" in result:
                    st.subheader("Dataset Preview")
                    st.dataframe(result["df"].head())

                # -----------------------------
                # Profile
                # -----------------------------
                if "profile" in result:
                    st.subheader("Dataset Profile")
                    st.dataframe(result["profile"])

                # -----------------------------
                # Plots (Optional)
                # -----------------------------
                if "figures" in result:

                    figs = result["figures"]

                    if "missing" in figs:
                        st.pyplot(figs["missing"])

                    if "numeric" in figs:
                        st.pyplot(figs["numeric"])

                    if "categorical" in figs:
                        st.pyplot(figs["categorical"])

                # -----------------------------
                # Download CSV
                # -----------------------------
                if "csv" in result:

                    with open(result["csv"], "rb") as f:

                        st.download_button(
                            label="⬇ Download Converted CSV",
                            data=f,
                            file_name=result["csv"].name,
                            use_container_width=True,
                        )

                # -----------------------------
                # Download Profile
                # -----------------------------
                if "profile_csv" in result:

                    with open(result["profile_csv"], "rb") as f:

                        st.download_button(
                            label="⬇ Download Profile Report",
                            data=f,
                            file_name=result["profile_csv"].name,
                            use_container_width=True,
                        )

            except Exception as e:

                st.error(f"Error processing {uploaded_file.name}")
                st.exception(e)

            progress.progress((index + 1) / len(uploaded_files))

        st.success("🎉 All datasets processed successfully!")