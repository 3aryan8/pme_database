"""Config loader: real singleton, strict Pydantic validation on ALL configs.

Importing ANY src module validates every config file (fail-fast at import).
"""
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.schemas import RegionClassConfig, SchemaConfig


class DenoiseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    method: str = "bilateral"
    params: Dict[str, Any] = Field(default_factory=dict)


class PreprocessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deskew: bool
    crop_to_content: bool
    contrast_equalization: bool
    denoise: DenoiseParams


class PdfSourcesConfig(BaseModel):
    """configs/pdf_sources.yaml — PDFs merged into the batched source."""
    model_config = ConfigDict(extra="forbid")
    pdfs: List[str] = Field(min_length=1)


class RenderingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    render_dpi: int = Field(ge=72, le=1200)  # CAP — each page renders at min(source effective DPI, this)
    vlm_long_edge_px: int = Field(ge=512, le=4096)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: Dict[str, str]
    paths: Dict[str, str]
    rendering: RenderingConfig
    preprocessing: PreprocessingConfig
    quality_checks: Dict[str, float]

    @field_validator("paths")
    @classmethod
    def required_paths(cls, v: Dict[str, str]) -> Dict[str, str]:
        required = {"raw_dir", "high_res_dir", "high_res_clean_dir",
                    "vlm_res_dir", "metadata_dir", "manifest_file"}
        missing = required - set(v)
        if missing:
            raise ValueError(f"pipeline.yaml 'paths' missing keys: {sorted(missing)}")
        return v


class ConfigLoader:
    _instance: "ConfigLoader | None" = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._load_configs()   # runs exactly once, ever
            cls._instance = inst
        return cls._instance

    def _load_configs(self) -> None:
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.config_dir = self.root_dir / "configs"

        def read(name: str) -> dict:
            path = self.config_dir / name
            if not path.exists():
                raise FileNotFoundError(f"Missing config file: {path}")
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            if not data:
                raise ValueError(f"Empty config file: {path}")
            return data

        self.pipeline = PipelineConfig(**read("pipeline.yaml"))
        self.pdf_sources = PdfSourcesConfig(**read("pdf_sources.yaml"))
        self.regions = RegionClassConfig(**read("regions.yaml"))
        self.schema = SchemaConfig(**read("schema.yaml"))
        self.models = read("models.yaml")  # raw: Group 2 owns its validation

    def get_path(self, key: str) -> Path:
        rel = self.pipeline.paths.get(key)
        if rel is None:
            raise KeyError(f"Path key '{key}' not found in pipeline.yaml")
        return (self.root_dir / rel).resolve()

    def get_preprocessing_param(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.pipeline.preprocessing.model_dump()
        for part in dotted_key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def bootstrap_dirs(self) -> None:
        """Create the data/ tree on fresh clones (git doesn't track empty dirs)."""
        for key in ("raw_dir", "merged_dir", "high_res_dir", "high_res_clean_dir",
                    "vlm_res_dir", "metadata_dir", "processed_dir"):
            self.get_path(key).mkdir(parents=True, exist_ok=True)


config = ConfigLoader()