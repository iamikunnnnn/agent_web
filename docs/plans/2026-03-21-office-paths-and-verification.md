# Office Paths And Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the office team use `.env`-driven directories and add explicit file verification plus Word read-before-edit guidance.

**Architecture:** Add a shared office config/path layer that resolves input and output directories from environment variables. Expose those helpers through a new office file toolkit, then attach that toolkit to the office team and specialists so Word/Markdown/PDF flows use the same directory rules and the leader can verify output files.

**Tech Stack:** `agno` agents/teams/toolkits, `python-dotenv`, `unittest`, `pathlib`, existing docx MCP

---

### Task 1: Lock env-driven path behavior with tests

**Files:**
- Modify: `tests/test_office_team_setup.py`
- Create: `tests/test_office_paths.py`

**Step 1: Write the failing test**

- Assert Markdown output falls under env-configured office markdown directory when no workspace is provided.
- Assert office file toolkit builds format-specific output paths from env.
- Assert office word agent and office team include the office file toolkit.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_paths tests.test_office_team_setup -v`
Expected: FAIL because the config/toolkit wiring does not exist yet.

**Step 3: Write minimal implementation**

- Add office config/path helpers and wire them into the toolkits/agents/team.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_paths tests.test_office_team_setup -v`
Expected: PASS.

### Task 2: Implement shared office config and file toolkit

**Files:**
- Create: `config/office_config.py`
- Create: `tools/office_file_toolkit.py`

**Step 1: Write the failing test**

- Assert office config reads env variables and derives default subdirectories.
- Assert office file toolkit exposes `get_office_paths`, `build_output_path`, `resolve_input_path`, and `file_exists`.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_paths -v`
Expected: FAIL until these modules exist.

**Step 3: Write minimal implementation**

- Build deterministic helpers for input/output directories and file existence checks.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_paths -v`
Expected: PASS.

### Task 3: Wire specialists and leader to the new path/verification layer

**Files:**
- Modify: `tools/office_markdown_toolkit.py`
- Modify: `tools/office_pdf_toolkit.py`
- Modify: `agent/office_word_agent.py`
- Modify: `agent/office_markdown_agent.py`
- Modify: `agent/office_pdf_agent.py`
- Modify: `team/office_team.py`
- Modify: `office_main.py`

**Step 1: Write the failing test**

- Assert office team exposes the shared file toolkit for leader-side verification.
- Assert office word agent tool list includes both the file toolkit and the docx MCP tool.
- Assert office main reads host/port/reload from office env config.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_paths tests.test_office_team_setup tests.test_office_main_entrypoint -v`
Expected: FAIL until wiring is complete.

**Step 3: Write minimal implementation**

- Update agents/team prompts and tools.
- Route Markdown/PDF saving through env-backed directory helpers.
- Make `office_main.py` serve using env-backed host/port/reload settings.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_paths tests.test_office_team_setup tests.test_office_main_entrypoint -v`
Expected: PASS.

### Task 4: Verify syntax and report env contract

**Files:**
- Modify only if verification reveals issues

**Step 1: Run focused tests**

Run: `python -m unittest tests.test_office_paths tests.test_office_team_setup tests.test_api_main_teams tests.test_office_main_entrypoint -v`
Expected: PASS.

**Step 2: Run syntax verification**

Run: `python -m py_compile config\office_config.py tools\office_file_toolkit.py tools\office_markdown_toolkit.py tools\office_pdf_toolkit.py agent\office_word_agent.py agent\office_markdown_agent.py agent\office_pdf_agent.py team\office_team.py office_main.py`
Expected: exit code 0.

**Step 3: Document env variables**

- Summarize required and optional `.env` keys in the final response.
