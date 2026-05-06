# Browser Workflow Transient DOM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep browser automation on a single-agent workflow while ensuring raw DOM and screenshot base64 are visible only in the current round and never persisted into later rounds.

**Architecture:** Use an Agno `Workflow` loop with `Observe -> Decide -> Execute -> Verify`. Persist only browser task context such as goal, iteration, last decision, last execution, last verification, and action history in workflow session state. Store raw DOM/screenshot payloads in a separate current-round state key, inject them into the agent prompt for the current `Decide` step only, and clear them after execution/verification or on error.

**Tech Stack:** Python, Agno Workflow, Pydantic, existing `web_driver_monitor` event bus/watchdog runtime, `unittest`.

---

### Task 1: Verify the rewritten single-agent workflow baseline

**Files:**
- Modify: `workflow/browser_workflow.py`
- Test: `server/web_driver_monitor/tests/test_browser_workflow.py`

**Step 1: Run targeted syntax and unit checks**

Run:
```bash
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m py_compile C:\Users\WUJIEAI\PycharmProjects\my_agents_newFeatureExplore\agent_manage\workflow\browser_workflow.py
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m unittest tests.test_browser_workflow -v
```

Expected:
- `py_compile` succeeds.
- Browser workflow tests fail where they still assume the old coordinator helper or old persistence behavior.

**Step 2: Confirm workflow registration still targets the browser workflow entrypoint**

Inspect:
- `api/init_workflow.py`

Expected:
- Workflow registration still calls `create_browser_workflow(workflow_id="browser_use_agent")`.

### Task 2: Update tests to lock the transient raw-state contract

**Files:**
- Modify: `server/web_driver_monitor/tests/test_browser_workflow.py`

**Step 1: Write failing tests for the current-round raw state**

Add tests that assert:
- `observe_current_page()` stores raw DOM/screenshot only under `_browser_workflow_current_round`.
- `observe_current_page()` returns a compact summary without raw DOM/base64 in `StepOutput.content`.
- `decide_browser_action()` uses persistent summary plus current-round raw payload in a string prompt.
- `verify_browser_progress()` clears `_browser_workflow_current_round`.
- `execute_browser_action()` preserves persistent action history without persisting raw DOM/base64.

**Step 2: Run the browser workflow tests and watch them fail for the expected reasons**

Run:
```bash
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m unittest tests.test_browser_workflow -v
```

Expected:
- New tests fail only because the workflow implementation or old tests are still mismatched.

### Task 3: Patch the workflow implementation only where behavior still leaks or mismatches tests

**Files:**
- Modify: `workflow/browser_workflow.py`

**Step 1: Keep the single-agent prompt contract explicit**

Ensure:
- Persistent state summary excludes raw DOM/base64.
- Current-round raw state includes DOM/base64 only for the current step.
- `normalize_browser_decision()` still provides deterministic fallback for direct URLs, known sites, and open-browser intents.

**Step 2: Clear raw state on all terminal/error paths**

Ensure:
- Errors in observe or execute clear `_browser_workflow_current_round`.
- `Verify` always clears `_browser_workflow_current_round`.
- `Execute` never writes raw observation into persistent state or returned content.

**Step 3: Re-run browser workflow tests**

Run:
```bash
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m unittest tests.test_browser_workflow -v
```

Expected:
- All browser workflow tests pass.

### Task 4: Re-run watchdog handle coverage and final verification

**Files:**
- Verify: `server/web_driver_monitor/tests/test_watchdog_handles.py`
- Verify: `server/web_driver_monitor/watchdogs/handles.py`
- Verify: `server/web_driver_monitor/watchdogs/__init__.py`

**Step 1: Run focused verification**

Run:
```bash
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m unittest tests.test_browser_workflow tests.test_watchdog_handles -v
```

Expected:
- All targeted tests pass.

**Step 2: Compile the touched workflow file**

Run:
```bash
C:\Users\WUJIEAI\miniconda3\envs\agent_api_newFeatureExplore\python.exe -m py_compile C:\Users\WUJIEAI\PycharmProjects\my_agents_newFeatureExplore\agent_manage\workflow\browser_workflow.py
```

Expected:
- No syntax errors.

### Task 5: Summarize the architecture delta

**Files:**
- Reference: `workflow/browser_workflow.py`
- Reference: `api/init_workflow.py`

**Step 1: Describe the final orchestration**

Summarize:
- Single-agent workflow loop remains on top of the existing bus/watchdog execution model.
- Browser runtime state remains in the browser/watchdog side.
- LLM-visible raw DOM/base64 is current-round only.
- Goal and action history remain persistent so the agent knows what it just did and what it is trying to accomplish.
