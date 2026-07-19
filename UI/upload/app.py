import streamlit as st

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="PCOS Canonical Schema Converter",
    layout="centered"
)


# -----------------------------
# Custom CSS
# -----------------------------
st.markdown(
    """
    <style>

    /* Main background */
    .stApp {
        background:
        radial-gradient(circle at 20% 20%, rgba(59,130,246,0.25), transparent 30%),
        radial-gradient(circle at 80% 80%, rgba(139,92,246,0.20), transparent 35%),
        #030712;
        color: white;
    }


    /* Hide Streamlit menu/footer */
    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }


    /* Main container */
    .block-container {
        max-width: 900px;
        padding-top: 4rem;
    }


    /* Title */
    .title {
        text-align:center;
        font-size: 3.2rem;
        font-weight: 800;
        color:white;
        letter-spacing:-1px;
    }


    .subtitle {
        text-align:center;
        color:#94a3b8;
        font-size:1.2rem;
        margin-bottom:3rem;
    }


    /* Glass card */
    .glass {

        background: rgba(255,255,255,0.06);
        backdrop-filter: blur(20px);

        border:
        1px solid rgba(255,255,255,0.12);

        border-radius:25px;

        padding:40px;

        box-shadow:
        0 20px 60px rgba(0,0,0,0.4);

    }


    /* Upload text */
    .upload-title {

        text-align:center;
        color:white;
        font-size:1.5rem;
        font-weight:600;

    }


    .upload-help {

        text-align:center;
        color:#94a3b8;

    }


    /* File cards */
    .file-card {

        background:rgba(255,255,255,0.05);

        border:
        1px solid rgba(255,255,255,0.1);

        padding:15px;

        border-radius:15px;

        margin-top:10px;

        color:white;

    }


    </style>
    """,
    unsafe_allow_html=True
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
    unsafe_allow_html=True
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
    unsafe_allow_html=True
)



uploaded_files = st.file_uploader(
    "",
    type=[
        "xpt",
        "csv",
        "xlsx",
        "xls"
    ],
    accept_multiple_files=True
)



# -----------------------------
# Show uploaded files
# -----------------------------
if uploaded_files:

    st.markdown(
        """
        <h3 style="color:white;">
        Uploaded Files
        </h3>
        """,
        unsafe_allow_html=True
    )


    for file in uploaded_files:

        size = file.size / 1024

        st.markdown(
            f"""
            <div class="file-card">

            📄 <b>{file.name}</b>

            <br>

            <span style="color:#94a3b8">
            {size:.1f} KB
            </span>

            <span style="float:right;color:#22c55e">
            ✓ Ready
            </span>

            </div>

            """,
            unsafe_allow_html=True
        )


    st.button(
        "Analyze Dataset →",
        use_container_width=True
    )