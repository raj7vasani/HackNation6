from pathlib import Path

def save_files(df, profile, output_dir, filename):

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    csv_file = output_dir / f"{filename}.csv"
    profile_file = output_dir / f"{filename}_profile.csv"

    df.to_csv(csv_file, index=False)
    profile.to_csv(profile_file, index=False)

    return csv_file, profile_file