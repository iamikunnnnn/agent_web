# Office Team Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new full office document team to `agent_manage` that follows the reference office-agent orchestration model while staying inside the current `agent_manage` architecture.

**Architecture:** Build a new `office_team` package around an `agno.Team` leader with five members: search specialist, Word specialist, Markdown specialist, PDF specialist, and leader orchestration. Reuse the existing DOCX MCP for Word work, add local Markdown/PDF toolkits for file generation, and register the team through the existing `api.main -> AgentOS` boot path.

**Tech Stack:** `agno` agents/teams, existing `docx_use_mcp` server, local Python toolkits, `reportlab`, `unittest`, `py_compile`

---

### Task 1: Lock the target shape with tests

**Files:**
- Modify: `tests/test_docx_team_setup.py`
- Modify: `tests/test_api_main_teams.py`
- Create: `tests/test_office_team_setup.py`

**Step 1: Write the failing test**

- Assert a new office team factory returns a team with five members.
- Assert each member has the expected role name and the expected primary tool family.
- Assert `api.main` passes `all_teams` containing the office team into `AgentOS`.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_team_setup tests.test_api_main_teams -v`

Expected: FAIL because the office team modules and registration do not exist yet.

**Step 3: Write minimal implementation**

- Create the new team/agent modules and wire them into `api.init_team`.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_team_setup tests.test_api_main_teams -v`

Expected: PASS.

### Task 2: Add office document toolkits

**Files:**
- Create: `tools/office_markdown_toolkit.py`
- Create: `tools/office_pdf_toolkit.py`
- Create: `tools/office_search_toolkit.py`

**Step 1: Write the failing test**

- Assert the Markdown toolkit exposes `save_markdown`.
- Assert the PDF toolkit exposes `generate_base_pdf`.
- Assert the search toolkit exposes at least one structured search entrypoint.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_team_setup -v`

Expected: FAIL because the toolkits do not exist yet.

**Step 3: Write minimal implementation**

- Implement local toolkits with stable names and return structures suited to office-agent prompts.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_team_setup -v`

Expected: PASS.

### Task 3: Implement office specialist agents

**Files:**
- Create: `agent/office_search_agent.py`
- Create: `agent/office_word_agent.py`
- Create: `agent/office_markdown_agent.py`
- Create: `agent/office_pdf_agent.py`

**Step 1: Write the failing test**

- Assert factories create agents with the expected IDs, names, system prompts, retries, and primary tools.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_team_setup -v`

Expected: FAIL until factories exist.

**Step 3: Write minimal implementation**

- Build each specialist with `get_ai_model()`, `create_base_db()`, `create_knowledge()`, and the relevant toolkit(s).

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_team_setup -v`

Expected: PASS.

### Task 4: Implement and register the office leader team

**Files:**
- Create: `team/office_team.py`
- Modify: `api/init_team.py`
- Modify: `api/main.py`

**Step 1: Write the failing test**

- Assert `create_office_team("office_team")` builds a leader team with the five specialists.
- Assert `api.main` includes the office team in `AgentOS(teams=...)` and monitoring `dbs_id`.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_office_team_setup tests.test_api_main_teams -v`

Expected: FAIL until team registration is complete.

**Step 3: Write minimal implementation**

- Add a new team factory and register it alongside existing teams.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_office_team_setup tests.test_api_main_teams -v`

Expected: PASS.

### Task 5: Verify syntax and integration boundaries

**Files:**
- Modify: only files touched above if verification reveals issues

**Step 1: Run focused tests**

Run: `python -m unittest tests.test_office_team_setup tests.test_api_main_teams -v`

Expected: PASS.

**Step 2: Run syntax verification**

Run: `python -m py_compile agent\office_search_agent.py agent\office_word_agent.py agent\office_markdown_agent.py agent\office_pdf_agent.py team\office_team.py api\init_team.py api\main.py tools\office_markdown_toolkit.py tools\office_pdf_toolkit.py tools\office_search_toolkit.py`

Expected: exit code 0.

**Step 3: Commit**

Not doing this automatically in this task.
