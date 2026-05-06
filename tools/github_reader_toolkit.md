# GitHubReaderToolkit (Minimal)

Purpose: provide only two capabilities for repo-RAG style systems:
1) Make a repo available locally (URL shallow-clone or use local path)
2) Parse a repo and classify files into `code` / `doc` / `other` with filters

This toolkit intentionally does **not** do embedding, chunking, or vector DB.

## Tools

### `prepare_repo(repo_url_or_path, repo_type=None, access_token=None, dest_root=None)`

Ensure the repository exists as a local directory.

- If `repo_url_or_path` is a local directory: returns it directly.
- If it is an URL: performs `git clone --depth=1 --single-branch` into `dest_root/<owner_repo>` (default: `~/.agent_manage/repos`).
- If `access_token` is provided: embeds it into the clone URL (best-effort) for private repos (token is sanitized from error messages).

Args:
- `repo_url_or_path` (str): repo URL (https) or local directory path
- `repo_type` (str|None): `github|gitlab|bitbucket|unknown` (optional; URL host auto-infer if omitted)
- `access_token` (str|None): token for private repos
- `dest_root` (str|None): local base directory for clones

Returns (dict):
- `repo_type`: inferred/used repo type
- `local_path`: absolute path to the local repo directory
- `used_existing`: whether it reused an existing local clone

### `parse_repo(repo_root, include_contents=False, excluded_dirs=None, excluded_files=None, included_dirs=None, included_files=None, max_file_bytes=..., max_tokens=...)`

Parse and classify repo files.

Design:
- **Classification by extension lists**:
  - `code`: common source extensions (`.py/.js/.ts/...`)
  - `doc`: common documentation/config extensions (`.md/.txt/.json/.yml/...`)
  - `other`: everything else (not read by default)
- **Filtering**:
  - Exclusion mode (default): remove common noise (VCS, venv, node_modules, build outputs, binaries, locks) + any custom exclusions you pass.
  - Inclusion mode: if you pass any of `included_dirs` or `included_files`, ONLY those directories/files are processed.
- **Safety**:
  - skips files larger than `max_file_bytes`
  - if `include_contents=True`, reads only `code/doc` and skips files whose token estimate exceeds `max_tokens`

Args:
- `repo_root` (str): local repo root directory
- `include_contents` (bool): whether to include file text in results; **default false** to avoid LLM context overflow
- `excluded_dirs` (str|None): comma/newline-separated directory names to exclude (path segment match)
- `excluded_files` (str|None): comma/newline-separated filename patterns to exclude (supports glob like `*.lock`)
- `included_dirs` (str|None): comma/newline-separated directory names to include (enables inclusion mode)
- `included_files` (str|None): comma/newline-separated filename patterns to include (enables inclusion mode)
- `max_file_bytes` (int): skip files larger than this size
- `max_tokens` (int): when reading content, skip files above this estimated token count

Returns (dict):
- `repo_root`: absolute normalized repo path
- `counts`: counts of `total/code/doc/other`
- `files`: list of objects:
  - `file_path` (repo-relative)
  - `category`: `code|doc|other`
  - `is_implementation`: heuristic flag for code files (tries to de-prioritize tests)
  - `token_count`: estimated tokens (only meaningful when `include_contents=True`)
  - `size_bytes`
  - `text` (only present when `include_contents=True`)

### `ingest_repo_to_knowledge(knowledge_id, repo_root, strategy="auto", categories="code,doc", ...)`

Ingest a repo into the project's configured Agno Knowledge base (VectorDb + Embedder) by:
1) parsing the repo tree into metadata (`code/doc/other`)
2) reading selected files
3) chunking them
4) writing chunks to a staging directory
5) calling `Knowledge.insert(path=staging_dir)`

This avoids pushing large file contents through tool parameters (prevents agent context overflow).

Args (core):
- `knowledge_id` (str): knowledge base id (usually your `agent.id`); determines PgVector table name
- `repo_root` (str): local repo root directory
- `strategy` (str): `auto|fixed|recursive|markdown|code`
  - `auto`: `.md` -> `markdown`, `code` files -> `code`, other docs -> `recursive`
- `categories` (str): which categories to ingest (default `code,doc`)
- `chunk_size` (int): chunk size in characters (default 4000)
- `overlap` (int): chunk overlap in characters (default 200)
- `max_file_bytes` (int): skip larger files (default 5MB)
- `staging_root` (str|None): where to write staging chunks (default `./user_cache/github_repo_reader_clone/staging_root_path/repo_kb_staging`)

Returns (dict):
- `knowledge_id`, `repo_root`, `staging_dir`
- `counts`: processed_files / created_chunks / skipped_files

Recommended usage:
- Always call `parse_repo(..., include_contents=False)` first to get a **file list**.
- Then read the specific files you need using the read tools below.

### `read_repo_file(repo_root, file_path, max_chars=20000, encoding="utf-8")`

Read a single file with a hard character cap to avoid context overflow.

Args:
- `repo_root` (str): local repo root directory
- `file_path` (str): repo-relative file path
- `max_chars` (int): returns at most this many characters
- `encoding` (str): decode encoding (errors replaced)

Returns (dict):
- `file_path`
- `truncated` (bool)
- `size_bytes`
- `content` (string)

### `read_repo_file_lines(repo_root, file_path, start_line=1, max_lines=200, encoding="utf-8")`

Read a line window from a file (safer than full content).

Args:
- `start_line` is 1-based

Returns (dict):
- `file_path`
- `start_line`
- `max_lines`
- `total_lines`
- `lines` (list[str])

## Typical flow

1) `prepare_repo(url_or_path)` -> get `local_path`
2) `parse_repo(local_path, include_contents=False, excluded_dirs=..., excluded_files=...)` -> choose candidate files
3) `read_repo_file_lines(local_path, "path/to/file.py", start_line=1, max_lines=200)` -> inspect
4) Repeat reads in small windows until you have enough context for chunking/DB ingestion
