from __future__ import annotations

"""
GitHubReaderToolkit (Minimal)

This module keeps only two capabilities for repo-style RAG pipelines:
1) Make a repository available locally (URL shallow-clone or use a local path)
2) Parse a repository tree and classify files into `code` / `doc` / `other`

It intentionally does NOT do embedding, chunking, vector DB, or multi-model logic.

Design note (avoid context overflow):
- `parse_repo(..., include_contents=False)` returns metadata only (paths + labels).
- Use `read_repo_file` / `read_repo_file_lines` to fetch a small slice on-demand.
"""

import fnmatch
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse, urlunparse

from agno.tools import Toolkit

RepoType = Literal["github", "gitlab", "bitbucket", "unknown"]


DEFAULT_EXCLUDED_DIRS: list[str] = [
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    ".idea",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "virtualenv",
    "node_modules",
    "bower_components",
    "jspm_packages",
    "dist",
    "build",
    "out",
    "target",
    "coverage",
    "htmlcov",
]

DEFAULT_EXCLUDED_FILES: list[str] = [
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.pyc",
    "*.pyd",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.zip",
    "*.gz",
    "*.tar",
    "*.tgz",
    "*.rar",
    "*.7z",
    "*.iso",
    "*.dmg",
    "*.lock",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "Cargo.lock",
    ".env",
    ".env.*",
    "*.env",
]

CODE_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".swift",
    ".html",
    ".css",
)

DOC_EXTENSIONS: tuple[str, ...] = (
    ".md",
    ".txt",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
)


def _safe_token_count(text: str) -> int:
    """
    Rough token estimate.
    - Prefer tiktoken if available.
    - Fallback to ~4 chars/token heuristic.
    """
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _normalize_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in re.split(r"[,\\n]+", value) if p.strip()]
    return parts or None


def _is_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False


def _infer_repo_type(repo_url: str) -> RepoType:
    host = (urlparse(repo_url).netloc or "").lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if "bitbucket" in host:
        return "bitbucket"
    return "unknown"


def _chunk_fixed(text: str, *, chunk_size: int, overlap: int = 0) -> list[str]:
    chunk_size = max(1, int(chunk_size))
    overlap = max(0, int(overlap))
    if not text:
        return []
    if chunk_size <= overlap:
        overlap = max(0, chunk_size // 4)
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _chunk_recursive(
    text: str,
    *,
    chunk_size: int,
    overlap: int = 0,
    separators: list[str] | None = None,
) -> list[str]:
    """
    A lightweight recursive chunker inspired by common RAG implementations.

    - Tries larger separators first, then falls back to fixed-size chunking.
    - Applies overlap only at the final fixed-size stage.
    """
    if not text or not text.strip():
        return []

    chunk_size = max(1, int(chunk_size))
    overlap = max(0, int(overlap))
    seps = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_once(t: str, sep: str) -> list[str]:
        if sep == "":
            return [t]
        return t.split(sep)

    def join_with_sep(parts: list[str], sep: str) -> list[str]:
        packed: list[str] = []
        cur: list[str] = []
        cur_len = 0
        for p in parts:
            if not p:
                continue
            add_len = len(p) + (len(sep) if cur else 0)
            if cur and cur_len + add_len > chunk_size:
                packed.append(sep.join(cur))
                cur = [p]
                cur_len = len(p)
            else:
                cur.append(p)
                cur_len += add_len
        if cur:
            packed.append(sep.join(cur))
        return packed

    segments = [text]
    for sep in seps:
        next_segments: list[str] = []
        changed = False
        for seg in segments:
            if len(seg) <= chunk_size:
                next_segments.append(seg)
                continue
            parts = split_once(seg, sep)
            if len(parts) == 1:
                next_segments.append(seg)
                continue
            changed = True
            next_segments.extend(join_with_sep(parts, sep))
        segments = next_segments
        if not changed:
            continue
        if all(len(s) <= chunk_size for s in segments):
            break

    chunks: list[str] = []
    for seg in segments:
        if len(seg) <= chunk_size:
            if seg.strip():
                chunks.append(seg)
        else:
            chunks.extend(_chunk_fixed(seg, chunk_size=chunk_size, overlap=overlap))
    return chunks


def _chunk_markdown(text: str, *, chunk_size: int, overlap: int = 0) -> list[str]:
    """
    Markdown-ish heading chunking:
    - Split on headings (#..######) and keep the heading line with its section.
    - For large sections, fall back to recursive chunking.
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    sections: list[list[str]] = []
    cur_lines: list[str] = []
    heading_re = re.compile(r"^(#{1,6})\\s+(.+?)\\s*$")

    for line in lines:
        if heading_re.match(line):
            if cur_lines:
                sections.append(cur_lines)
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_lines:
        sections.append(cur_lines)

    chunks: list[str] = []
    for sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue
        if len(sec_text) <= chunk_size:
            chunks.append(sec_text)
        else:
            chunks.extend(
                _chunk_recursive(
                    sec_text,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )
            )
    return chunks


def _chunk_code(text: str, *, chunk_size: int, overlap: int = 0, language: str | None = None) -> list[str]:
    """
    Heuristic code chunking:
    - Prefer splitting on top-level function/class boundaries for Python.
    - For other languages, split on 'function'/'class'/'export' boundaries (best-effort).
    - Falls back to recursive chunking.
    """
    if not text or not text.strip():
        return []

    lang = (language or "").lower()
    lines = text.splitlines()

    split_indices: list[int] = [0]
    if lang in {"py", "python"}:
        boundary = re.compile(r"^(def|class)\\s+\\w+")
        for i, line in enumerate(lines):
            if i == 0:
                continue
            if boundary.match(line):
                split_indices.append(i)
    else:
        boundary = re.compile(r"^\\s*(export\\s+)?(async\\s+)?(function|class)\\b")
        for i, line in enumerate(lines):
            if i == 0:
                continue
            if boundary.match(line):
                split_indices.append(i)

    split_indices = sorted(set(split_indices))
    split_indices.append(len(lines))

    pieces: list[str] = []
    for a, b in zip(split_indices, split_indices[1:], strict=False):
        piece = "\n".join(lines[a:b]).strip()
        if piece:
            pieces.append(piece)

    if len(pieces) <= 1:
        return _chunk_recursive(text, chunk_size=chunk_size, overlap=overlap)

    chunks: list[str] = []
    for p in pieces:
        if len(p) <= chunk_size:
            chunks.append(p)
        else:
            chunks.extend(_chunk_recursive(p, chunk_size=chunk_size, overlap=overlap))
    return chunks


def _guess_language_from_path(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    if ext == ".py":
        return "python"
    if ext in {".js", ".jsx"}:
        return "javascript"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext == ".go":
        return "go"
    if ext == ".rs":
        return "rust"
    if ext in {".c", ".h"}:
        return "c"
    if ext in {".cpp", ".hpp"}:
        return "cpp"
    if ext == ".java":
        return "java"
    return None


def _safe_read_text(path: Path, *, max_bytes: int, encoding: str = "utf-8") -> str | None:
    try:
        if path.stat().st_size > max(0, int(max_bytes)):
            return None
        return path.read_text(encoding=encoding, errors="replace")
    except Exception:
        return None

# todo 修复staging 不会被自动删除的问题，应在成功后删除，避免staging 的大量累计。
def _write_ingest_chunk(
    out_dir: Path,
    *,
    repo_root: str,
    file_path: str,
    category: str,
    chunk_index: int,
    text: str,
) -> Path:
    """
    Write a single chunk as a markdown file with a lightweight metadata header.

    Using a file-based staging area lets us rely on `Knowledge.insert(path=...)`
    without depending on internal VectorDb/Knowledge APIs across Agno versions.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", file_path)[:120]
    out_path = out_dir / f"{safe_name}__chunk_{chunk_index:05d}.md"

    header = (
        "---\n"
        f"repo_root: {repo_root}\n"
        f"file_path: {file_path}\n"
        f"category: {category}\n"
        f"chunk_index: {chunk_index}\n"
        "---\n\n"
    )

    out_path.write_text(header + text, encoding="utf-8", errors="replace")
    return out_path


def _repo_name_from_url(repo_url: str) -> str:
    parts = repo_url.rstrip("/").split("/")
    # Try to return owner_repo for uniqueness; fallback to last segment.
    if len(parts) >= 2:
        owner = parts[-2]
        repo = parts[-1].removesuffix(".git")
        return f"{owner}_{repo}"
    return parts[-1].removesuffix(".git")


def _with_token(repo_url: str, repo_type: RepoType, access_token: str) -> str:
    """
    Embed token in clone URL for private repos, without trying to be overly clever.
    """
    parsed = urlparse(repo_url)
    encoded = quote(access_token, safe="")
    if repo_type == "gitlab":
        # Common GitLab format: https://oauth2:TOKEN@gitlab.com/group/repo.git
        netloc = f"oauth2:{encoded}@{parsed.netloc}"
    else:
        # GitHub/Bitbucket typically accept: https://TOKEN@host/owner/repo.git
        netloc = f"{encoded}@{parsed.netloc}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _run_git_clone(clone_url: str, dest_dir: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth=1", "--single-branch", clone_url, str(dest_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _should_process_path(
    *,
    rel_path: str,
    use_inclusion_mode: bool,
    included_dirs: list[str] | None,
    included_files: list[str] | None,
    excluded_dirs: list[str] | None,
    excluded_files: list[str] | None,
) -> bool:
    rel_parts = Path(rel_path).parts
    filename = Path(rel_path).name

    if use_inclusion_mode:
        # Included dirs match any path segment (simple but effective).
        if included_dirs:
            for d in included_dirs:
                clean = d.strip("./\\").rstrip("/\\")
                if not clean:
                    continue
                if clean in rel_parts:
                    return True
        if included_files:
            for pat in included_files:
                if filename == pat or fnmatch.fnmatch(filename, pat):
                    return True
        # If inclusion mode requested but no rules provided, allow everything.
        return not (included_dirs or included_files)

    # Exclusion mode
    if excluded_dirs:
        for d in excluded_dirs:
            clean = d.strip("./\\").rstrip("/\\")
            if not clean:
                continue
            if clean in rel_parts:
                return False

    if excluded_files:
        for pat in excluded_files:
            if filename == pat or fnmatch.fnmatch(filename, pat):
                return False

    return True


@dataclass
class ParsedFile:
    file_path: str
    category: Literal["code", "doc", "other"]
    is_implementation: bool
    token_count: int
    size_bytes: int
    text: str | None = None


def parse_repo_tree(
    repo_root: str | Path,
    *,
    include_contents: bool = True,
    excluded_dirs: list[str] | None = None,
    excluded_files: list[str] | None = None,
    included_dirs: list[str] | None = None,
    included_files: list[str] | None = None,
    max_file_bytes: int = 5 * 1024 * 1024,
    max_tokens: int = 8192 * 10,
    encoding: str = "utf-8",
) -> list[ParsedFile]:
    """
    Read & classify a repository into "code"/"doc"/"other" files.

    Philosophy (matching the referenced github_reader/data_pipeline approach):
    - Classify by extension lists (fast, predictable).
    - Filter aggressively (exclude vendor/build/binary/noise).
    - Skip very large files early.
    - Attach metadata that helps retrieval later: token_count, is_implementation, etc.
    """
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"repo_root is not a directory: {root}")

    excluded_dirs = list(dict.fromkeys((excluded_dirs or []) + DEFAULT_EXCLUDED_DIRS))
    excluded_files = list(dict.fromkeys((excluded_files or []) + DEFAULT_EXCLUDED_FILES))

    use_inclusion_mode = bool((included_dirs and len(included_dirs) > 0) or (included_files and len(included_files) > 0))

    results: list[ParsedFile] = []

    # Deterministic traversal order helps reproducibility.
    all_files = sorted([p for p in root.rglob("*") if p.is_file()], key=lambda p: str(p).lower())

    for path in all_files:
        rel = str(path.relative_to(root))

        if not _should_process_path(
            rel_path=rel,
            use_inclusion_mode=use_inclusion_mode,
            included_dirs=included_dirs,
            included_files=included_files,
            excluded_dirs=excluded_dirs,
            excluded_files=excluded_files,
        ):
            continue

        try:
            size = path.stat().st_size
        except Exception:
            continue

        if size > max_file_bytes:
            continue

        ext = path.suffix.lower()
        if ext in CODE_EXTENSIONS:
            category: Literal["code", "doc", "other"] = "code"
        elif ext in DOC_EXTENSIONS:
            category = "doc"
        else:
            category = "other"

        # Their heuristic: "implementation" tries to avoid test/app scaffolding.
        rel_lower = rel.lower()
        is_implementation = (
            category == "code"
            and not Path(rel).name.startswith("test_")
            and "test" not in rel_lower
            and not Path(rel).name.startswith("app_")
        )

        text: str | None = None
        token_count = 0
        if include_contents and category in {"code", "doc"}:
            try:
                text = path.read_text(encoding=encoding, errors="replace")
                token_count = _safe_token_count(text)
                if token_count > max_tokens:
                    continue
            except Exception:
                # Keep metadata-only record if desired later; for now skip unreadable files.
                continue

        results.append(
            ParsedFile(
                file_path=rel,
                category=category,
                is_implementation=is_implementation,
                token_count=token_count,
                size_bytes=size,
                text=text,
            )
        )

    return results


def prepare_repo_locally(
    repo_url_or_path: str,
    *,
    repo_type: RepoType | None = None,
    access_token: str | None = None,
    dest_root: str | Path | None = None,
) -> dict[str, Any]:
    """
    Ensure repo is available as a local directory.
    - If input is a local path, return it.
    - If input is a URL, shallow clone to dest_root/<owner_repo>.
    """
    src = (repo_url_or_path or "").strip()
    if not src:
        raise ValueError("repo_url_or_path is required")

    if not _is_url(src):
        p = Path(src).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Local repo path not found: {p}")
        return {"repo_type": "unknown", "local_path": str(p), "used_existing": True}

    inferred = _infer_repo_type(src)
    rt: RepoType = repo_type or inferred

    root = Path(dest_root or Path.home() / ".agent_manage" / "repos").expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    name = _repo_name_from_url(src)
    dest = root / name

    if dest.exists() and any(dest.iterdir()):
        return {"repo_type": rt, "local_path": str(dest), "used_existing": True}

    clone_url = src
    if access_token:
        clone_url = _with_token(src, rt, access_token)

    try:
        _run_git_clone(clone_url, dest)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        if access_token:
            stderr = stderr.replace(access_token, "***TOKEN***")
            stderr = stderr.replace(quote(access_token, safe=""), "***TOKEN***")
        raise ValueError(f"git clone failed: {stderr}") from exc

    return {"repo_type": rt, "local_path": str(dest), "used_existing": False}


class GitHubReaderToolkit(Toolkit):
    """
    Minimal toolkit that keeps only:
    1) Fetching a repo (URL -> local shallow clone, or local path)
    2) Parsing repo files and classifying code/docs for downstream chunking/database work
    """

    def __init__(self, name: str = "GitHubReaderToolkit", *args, **kwargs) -> None:
        tools = [
            self.prepare_repo,
            self.parse_repo,
            self.read_repo_file,
            self.read_repo_file_lines,
            self.ingest_repo_to_knowledge,
        ]
        super().__init__(name=name, tools=tools, *args, **kwargs)

    def prepare_repo(
        self,
        repo_url_or_path: str,
        repo_type: str | None = None,
        access_token: str | None = None,
        dest_root: str | None = None,
    ) -> dict[str, Any]:
        """
        Ensure a repository is available as a local directory.

        Behavior:
        - If `repo_url_or_path` points to an existing local directory: returns it directly.
        - If it is a URL: performs a shallow clone (`git clone --depth=1 --single-branch`)
          into `dest_root` (default: `~/.agent_manage/repos/<owner_repo>`).

        Args:
        - repo_url_or_path: HTTPS repo URL or local directory path.
        - repo_type: Optional hint (`github|gitlab|bitbucket|unknown`). If omitted, inferred from URL host.
        - access_token: Optional token for private repos. Best-effort embedded into the clone URL.
        - dest_root: Optional local base directory for clones.

        Returns:
        - repo_type: inferred/used type
        - local_path: absolute local repo path
        - used_existing: whether an existing clone was reused
        """
        rt: RepoType | None
        if repo_type is None:
            rt = None
        else:
            lower = repo_type.strip().lower()
            rt = lower if lower in {"github", "gitlab", "bitbucket", "unknown"} else "unknown"  # type: ignore[assignment]
        return prepare_repo_locally(
            repo_url_or_path,
            repo_type=rt,
            access_token=access_token,
            dest_root=dest_root,
        )

    def parse_repo(
        self,
        repo_root: str,
        include_contents: bool = False,
        excluded_dirs: str | None = None,
        excluded_files: str | None = None,
        included_dirs: str | None = None,
        included_files: str | None = None,
        max_file_bytes: int = 5 * 1024 * 1024,
        max_tokens: int = 8192 * 10,
    ) -> dict[str, Any]:
        """
        Parse and classify repository files, producing a JSON-friendly index for downstream RAG pipelines.

        Primary goal: return *paths + labels* without flooding the agent context.
        - Default `include_contents=False` returns metadata only.
        - If you need actual text, prefer `read_repo_file` / `read_repo_file_lines` on-demand.

        Filters:
        - Exclusion mode (default): remove common noise directories/files plus any custom exclusions.
        - Inclusion mode: if `included_dirs` or `included_files` is provided, ONLY those are processed.

        Args:
        - repo_root: local repo root directory.
        - include_contents: whether to include `text` for `code/doc` files (default: False).
        - excluded_dirs: comma/newline-separated directory names to exclude (path segment match).
        - excluded_files: comma/newline-separated filename patterns to exclude (supports glob like `*.lock`).
        - included_dirs: comma/newline-separated directory names to include (enables inclusion mode).
        - included_files: comma/newline-separated filename patterns to include (enables inclusion mode).
        - max_file_bytes: skip files larger than this size.
        - max_tokens: when `include_contents=True`, skip files above this estimated token count.

        Returns:
        - repo_root: absolute normalized repo root path
        - counts: total/code/doc/other counts
        - files: list of {file_path, category, is_implementation, token_count, size_bytes, (optional) text}
        """
        parsed = parse_repo_tree(
            repo_root,
            include_contents=include_contents,
            excluded_dirs=_normalize_csv_list(excluded_dirs),
            excluded_files=_normalize_csv_list(excluded_files),
            included_dirs=_normalize_csv_list(included_dirs),
            included_files=_normalize_csv_list(included_files),
            max_file_bytes=max_file_bytes,
            max_tokens=max_tokens,
        )

        # Return JSON-friendly structure.
        include_text = bool(include_contents)
        return {
            "repo_root": str(Path(repo_root).expanduser().resolve()),
            "counts": {
                "total": len(parsed),
                "code": sum(1 for f in parsed if f.category == "code"),
                "doc": sum(1 for f in parsed if f.category == "doc"),
                "other": sum(1 for f in parsed if f.category == "other"),
            },
            "files": [
                {
                    "file_path": f.file_path,
                    "category": f.category,
                    "is_implementation": f.is_implementation,
                    "token_count": f.token_count,
                    "size_bytes": f.size_bytes,
                    **({"text": f.text} if include_text else {}),
                }
                for f in parsed
            ],
        }

    def _resolve_repo_file(self, repo_root: str, file_path: str) -> Path:
        root = Path(repo_root).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"repo_root is not a directory: {root}")
        candidate = (root / file_path).resolve()
        # Prevent path traversal: candidate must be inside root.
        if root != candidate and root not in candidate.parents:
            raise ValueError("file_path escapes repo_root")
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"file not found: {file_path}")
        return candidate

    def read_repo_file(
        self,
        repo_root: str,
        file_path: str,
        *,
        max_chars: int = 20000,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        Read a single file from a repo with a hard cap, to avoid agent context overflow.
        Returns the first `max_chars` characters (decoded with errors='replace').
        """
        p = self._resolve_repo_file(repo_root, file_path)
        raw = p.read_text(encoding=encoding, errors="replace")
        content = raw[: max(0, int(max_chars))]
        return {
            "repo_root": str(Path(repo_root).expanduser().resolve()),
            "file_path": file_path,
            "truncated": len(content) < len(raw),
            "size_bytes": p.stat().st_size,
            "content": content,
        }

    def read_repo_file_lines(
        self,
        repo_root: str,
        file_path: str,
        *,
        start_line: int = 1,
        max_lines: int = 200,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        Read a single file by line window (1-based start_line).
        Safer than returning the full file content.
        """
        p = self._resolve_repo_file(repo_root, file_path)
        lines = p.read_text(encoding=encoding, errors="replace").splitlines()
        s = max(1, int(start_line))
        n = max(0, int(max_lines))
        window = lines[s - 1 : s - 1 + n]
        return {
            "repo_root": str(Path(repo_root).expanduser().resolve()),
            "file_path": file_path,
            "start_line": s,
            "max_lines": n,
            "total_lines": len(lines),
            "lines": window,
        }

    def ingest_repo_to_knowledge(
        self,
        repo_root: str,
        *,
        strategy: str = "auto",
        categories: str = "code,doc",
        excluded_dirs: str | None = None,
        excluded_files: str | None = None,
        included_dirs: str | None = None,
        included_files: str | None = None,
        chunk_size: int = 4000,
        overlap: int = 200,
        max_file_bytes: int = 5 * 1024 * 1024,
        staging_root: str | None = None,
    ) -> dict[str, Any]:
        """
        Ingest a repo into an Agno Knowledge base (vector DB) using the project's configured VectorDb + Embedder.

        This tool uses `parse_repo_tree` metadata to decide what to read, then creates a *staging directory*
        of chunk files and calls `Knowledge.insert(path=staging_dir)`.

        Why staging files:
        - Avoids passing huge texts via tool parameters (prevents agent context overflow).
        - Minimizes coupling to internal `VectorDb`/`Knowledge` APIs across Agno versions.
        - Preserves provenance via a YAML header embedded in each chunk.

        Args:
        - repo_root: Local repo root directory.
        - strategy: `auto|fixed|recursive|markdown|code`.
          - `auto`: markdown for `.md`, code chunking for code files, recursive for other docs.
        - categories: comma/newline-separated categories to ingest (default: `code,doc`).
        - excluded_dirs/excluded_files/included_dirs/included_files: same semantics as `parse_repo`.
        - chunk_size/overlap: chunking parameters (character-based).
        - max_file_bytes: skip files larger than this size.
        - staging_root: where to write staging chunks (default: `./user_cache/github_repo_reader_clone/staging_root_path/repo_kb_staging`).

        Returns:
        - agent_id, repo_root
        - staging_dir: the directory inserted into Knowledge
        - counts: processed_files / created_chunks / skipped_files
        """
        from config.db_config import create_knowledge
        # 硬编码agent_id
        agent_id = "github_reader_agent"

        repo_root_path = Path(repo_root).expanduser().resolve()
        if not repo_root_path.exists() or not repo_root_path.is_dir():
            raise ValueError(f"repo_root is not a directory: {repo_root_path}")

        selected_categories = {
            c.strip().lower() for c in (_normalize_csv_list(categories) or []) if c.strip()
        }
        if not selected_categories:
            selected_categories = {"code", "doc"}

        parsed = parse_repo_tree(
            repo_root_path,
            include_contents=False,
            excluded_dirs=_normalize_csv_list(excluded_dirs),
            excluded_files=_normalize_csv_list(excluded_files),
            included_dirs=_normalize_csv_list(included_dirs),
            included_files=_normalize_csv_list(included_files),
            max_file_bytes=max_file_bytes,
            max_tokens=10**18,
        )

        if staging_root is None:
            staging_root_path = Path("./user_cache/github_repo_reader_clone/staging_root_path/repo_kb_staging").resolve()
        else:
            staging_root_path = Path(staging_root).expanduser().resolve()

        repo_name = repo_root_path.name
        staging_dir = staging_root_path / agent_id / repo_name / time.strftime("%Y%m%d_%H%M%S")
        staging_dir.mkdir(parents=True, exist_ok=True)

        strategy_norm = strategy.strip().lower()
        processed_files = 0
        created_chunks = 0
        skipped_files: list[dict[str, Any]] = []

        for f in parsed:
            if f.category not in selected_categories:
                continue

            abs_path = (repo_root_path / f.file_path).resolve()
            text = _safe_read_text(abs_path, max_bytes=max_file_bytes)
            if text is None or not text.strip():
                skipped_files.append({"file_path": f.file_path, "reason": "too_large_or_unreadable"})
                continue

            if strategy_norm == "auto":
                if Path(f.file_path).suffix.lower() == ".md":
                    file_strategy = "markdown"
                elif f.category == "code":
                    file_strategy = "code"
                else:
                    file_strategy = "recursive"
            else:
                file_strategy = strategy_norm

            if file_strategy == "fixed":
                chunks = _chunk_fixed(text, chunk_size=chunk_size, overlap=overlap)
            elif file_strategy == "recursive":
                chunks = _chunk_recursive(text, chunk_size=chunk_size, overlap=overlap)
            elif file_strategy == "markdown":
                chunks = _chunk_markdown(text, chunk_size=chunk_size, overlap=overlap)
            elif file_strategy == "code":
                lang = _guess_language_from_path(f.file_path)
                chunks = _chunk_code(text, chunk_size=chunk_size, overlap=overlap, language=lang)
            else:
                chunks = _chunk_recursive(text, chunk_size=chunk_size, overlap=overlap)

            if not chunks:
                skipped_files.append({"file_path": f.file_path, "reason": "empty_after_chunking"})
                continue

            processed_files += 1
            for idx, chunk in enumerate(chunks):
                _write_ingest_chunk(
                    staging_dir,
                    repo_root=str(repo_root_path),
                    file_path=f.file_path,
                    category=f.category,
                    chunk_index=idx,
                    text=chunk,
                )
                created_chunks += 1

        knowledge = create_knowledge(
            id=agent_id,
            name=agent_id,
            description=f"Knowledge base for {agent_id}",
        )
        knowledge.insert(path=str(staging_dir))

        return {
            "agent_id": agent_id,
            "repo_root": str(repo_root_path),
            "staging_dir": str(staging_dir),
            "counts": {
                "processed_files": processed_files,
                "created_chunks": created_chunks,
                "skipped_files": len(skipped_files),
            },
            "skipped": skipped_files[:50],
        }
