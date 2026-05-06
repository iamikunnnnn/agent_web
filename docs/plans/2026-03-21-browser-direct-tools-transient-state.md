# Browser Direct Tools Transient State Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore `browser_use_agent` to direct browser tool-calling while ensuring raw DOM/base64 survive only within the current run round and never accumulate in persisted tool history.

**Architecture:** Remove `browser_use_agent` from workflow registration and expose it again as a normal agent with browser tools. Browser tools will return compact summaries to the model, while writing the latest raw browser snapshot into a fixed transient `session_state` key that is cleared by a pre-hook at the start of each run.

**Tech Stack:** Agno Agent, Agno RunContext/session_state, existing `web_driver_monitor` tools, Python `unittest`.

---
