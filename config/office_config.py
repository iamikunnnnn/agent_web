from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_office_paths() -> dict[str, Path]:
    base_dir = Path(os.getenv("OFFICE_BASE_DIR", _project_root() / "docs" / "office")).expanduser()
    input_dir = Path(os.getenv("OFFICE_INPUT_DIR", base_dir / "input")).expanduser()
    output_dir = Path(os.getenv("OFFICE_OUTPUT_DIR", base_dir / "output")).expanduser()

    paths = {
        "base_dir": base_dir,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "docx_output_dir": Path(os.getenv("OFFICE_DOCX_OUTPUT_DIR", output_dir / "docx")).expanduser(),
        "markdown_output_dir": Path(os.getenv("OFFICE_MARKDOWN_OUTPUT_DIR", output_dir / "markdown")).expanduser(),
        "pdf_output_dir": Path(os.getenv("OFFICE_PDF_OUTPUT_DIR", output_dir / "pdf")).expanduser(),
        "search_output_dir": Path(os.getenv("OFFICE_SEARCH_OUTPUT_DIR", output_dir / "search")).expanduser(),
    }
    return {name: path.resolve() for name, path in paths.items()}


def ensure_office_dirs() -> dict[str, Path]:
    paths = get_office_paths()
    for key, path in paths.items():
        if key.endswith("_dir"):
            path.mkdir(parents=True, exist_ok=True)
    return paths


def office_output_dir_for(kind: str) -> Path:
    paths = ensure_office_dirs()
    mapping = {
        "docx": paths["docx_output_dir"],
        "md": paths["markdown_output_dir"],
        "markdown": paths["markdown_output_dir"],
        "pdf": paths["pdf_output_dir"],
        "search": paths["search_output_dir"],
    }
    return mapping.get(kind.lower(), paths["output_dir"])


def office_extension_for(kind: str) -> str:
    mapping = {
        "docx": ".docx",
        "md": ".md",
        "markdown": ".md",
        "pdf": ".pdf",
        "search": ".json",
    }
    return mapping.get(kind.lower(), "")


def build_office_output_path(file_name: str, kind: str) -> Path:
    safe_name = Path(file_name).name or f"office_output{office_extension_for(kind)}"
    extension = office_extension_for(kind)
    if extension and not safe_name.lower().endswith(extension):
        safe_name = f"{safe_name}{extension}"
    return (office_output_dir_for(kind) / safe_name).resolve()


def resolve_office_input_path(file_name: str) -> Path:
    path = Path(file_name).expanduser()
    if path.is_absolute():
        return path.resolve()
    paths = ensure_office_dirs()
    return (paths["input_dir"] / path.name).resolve()


def get_office_main_settings() -> dict[str, object]:
    return {
        "host": os.getenv("OFFICE_MAIN_HOST", "0.0.0.0"),
        "port": int(os.getenv("OFFICE_MAIN_PORT", "7778")),
        "reload": _as_bool(os.getenv("OFFICE_MAIN_RELOAD"), True),
    }
