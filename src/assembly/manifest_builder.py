"""Writes manifest.parquet. Every row passes the AssemblyRow Pydantic
contract BEFORE being written — the parquet on disk is guaranteed valid."""
import pandas as pd

from src.models.schemas import AssemblyRow
from src.utils.config_loader import config


def write_manifest(rows: list) -> object:
    validated = [AssemblyRow(**r).model_dump() for r in rows]
    df = pd.DataFrame(validated)
    out = config.get_path("manifest_file")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out