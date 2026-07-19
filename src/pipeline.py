from pathlib import Path

from .loader import load_dataset
from .profiler import create_profile
from .exporter import save_files


def process_file(file_path):

    file_path = Path(file_path)

    # Load XPT/CSV/Excel
    df = load_dataset(file_path)

    # Create profile dataframe
    profile = create_profile(df)

    # Save files
    csv_path, profile_path = save_files(
        df,
        profile,
        "outputs",
        file_path.stem
    )

    return {
        "df": df,                    # dataframe for st.dataframe()
        "profile": profile,          # dataframe for st.dataframe()
        "csv": csv_path,             # path for download
        "profile_csv": profile_path  # path for download
    }