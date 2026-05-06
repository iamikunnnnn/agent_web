# Browser Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current browser agent with an Agno Workflow that keeps browser/page state in the runtime but keeps DOM observation stateless and summarized between workflow steps.

**Architecture:** Build a browser workflow with a looped `observe -> decide -> execute -> verify` pipeline. The observer step reads the current browser snapshot and returns a compact structured observation, the coordinator agent decides the next action from that compact observation only, and the executor step performs exactly one browser action against the existing `web_driver_monitor` service.

**Tech Stack:** Python, Agno Agent/Workflow, FastAPI AgentOS, Playwright-backed `web_driver_monitor`, pytest

---

### Task 1: Add regression tests for stateless browser observation

**Files:**
- Create: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tests/test_browser_workflow.py`
- Reference: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tools/web_driver_monitor_toolkit.py`
- Reference: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/server/web_driver_monitor/watchdogs/page_actions.py`

**Step 1: Write the failing tests**

Add tests that prove:
- the observer summary removes raw `screenshot_base64`
- the observer summary reduces DOM to compact candidate/action data
- the executor step can consume a coordinator decision without needing prior raw DOM in context
- the workflow loop stop condition stops once a step requests `stop=True`

**Step 2: Run the tests to verify they fail**

Run:
```bash
pytest C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tests/test_browser_workflow.py -q
```

Expected: FAIL because browser workflow helpers and workflow object do not exist yet.

### Task 2: Implement workflow helpers and compact browser state protocol

**Files:**
- Create: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/workflow/browser_workflow.py`
- Modify: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tools/web_driver_monitor_toolkit.py`
- Optional Modify: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/server/web_driver_monitor/watchdogs/page_actions.py`

**Step 1: Add compact snapshot helpers**

Implement helpers that:
- strip `screenshot_base64` from LLM-facing content
- summarize DOM into a stable schema such as `url`, `element_count`, `top_interactables`, `high_value_candidates`
- preserve full raw tool responses only in executor/internal metadata, not in coordinator-facing content

**Step 2: Add workflow executor helpers**

Implement function steps for:
- `observe_current_page(step_input, session_state, run_context)`
- `execute_browser_action(step_input, session_state, run_context)`
- `verify_browser_progress(step_input, session_state, run_context)`

Each function should return a `StepOutput` with small structured content and use `stop=True` when the workflow should end.

**Step 3: Add a coordinator agent**

Create a dedicated planning/coordinator agent that:
- sees only compact observation content
- emits one next action at a time in structured JSON-like form
- does not receive full prior DOM or screenshot blobs

**Step 4: Build the workflow**

Create a workflow with:
- a loop over `Observe`, `Decide`, `Execute`, `Verify`
- bounded `max_iterations`
- an end condition driven by `StepOutput.stop`

**Step 5: Run the targeted tests**

Run:
```bash
pytest C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tests/test_browser_workflow.py -q
```

Expected: PASS

### Task 3: Integrate the workflow into AgentOS

**Files:**
- Create: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/init_workflow.py`
- Modify: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/init_agent.py`
- Modify: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/main.py`

**Step 1: Register the workflow**

Expose the new browser workflow from a dedicated workflow initializer module.

**Step 2: Wire the workflow into AgentOS**

Pass the browser workflow via the `workflows=[...]` argument when constructing `AgentOS`.

**Step 3: Keep the old browser agent isolated or remove it**

The default browser path should favor the workflow and avoid the old single-agent DOM accumulation path.

**Step 4: Smoke-check imports**

Run:
```bash
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/workflow/browser_workflow.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/init_workflow.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/init_agent.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/main.py
```

Expected: no syntax errors

### Task 4: Verify end-to-end behavior and guard against context explosion

**Files:**
- Reference: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/main.py`
- Reference: `C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/workflow/browser_workflow.py`

**Step 1: Run the targeted tests again**

Run:
```bash
pytest C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tests/test_browser_workflow.py -q
```

Expected: PASS

**Step 2: Run import verification**

Run:
```bash
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/workflow/browser_workflow.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/tools/web_driver_monitor_toolkit.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/init_workflow.py
python -m py_compile C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/main.py
```

Expected: PASS

**Step 3: Manual runtime check**

Start the app and verify:
- the browser workflow is listed in AgentOS routes
- runs produce workflow step events
- observer output no longer includes raw `screenshot_base64`
- coordinator history contains compact summaries rather than raw DOM dumps
