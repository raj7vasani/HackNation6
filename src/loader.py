import pandas as pd
from pathlib import Path

def load_dataset(path):
    path = Path(path)

    if path.suffix.lower() == ".xpt":
        return pd.read_sas(path, format="xport")

    elif path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    elif path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(path)

    else:
        raise ValueError("Unsupported file type")