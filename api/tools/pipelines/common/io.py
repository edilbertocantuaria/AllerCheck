import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def _get_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_with_timestamp(data: dict | pd.DataFrame, output_dir: Path, base_name: str, extension: str = "json") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _get_timestamp()
    filename = f"{timestamp}_{base_name}.{extension}"
    filepath = output_dir / filename

    if isinstance(data, pd.DataFrame):
        if extension == "csv":
            data.to_csv(filepath, index=False, encoding="utf-8")
        elif extension == "xlsx":
            data.to_excel(filepath, index=False)
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath


def load_file(filepath: Path) -> dict | pd.DataFrame:
    if filepath.suffix == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    elif filepath.suffix in {".csv", ".xlsx"}:
        return pd.read_csv(filepath) if filepath.suffix == ".csv" else pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported format: {filepath.suffix}")
