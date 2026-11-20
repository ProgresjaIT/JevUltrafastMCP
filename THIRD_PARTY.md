# Upstream provenance

Adapted from https://github.com/browser-use/jev-ultrafast
Revision: cf3c406f0fc4becff8986ed4d4d37b7b9f102e45 (retrieved 2026-11-20).
License: MIT, preserved verbatim in LICENSE.upstream.

The jev_ultrafast package retains the original indexed snapshot, questions,
operation/target selection, action guards and agent loop. Local changes replace
Browser Harness with Playwright CDP, replace the generic text provider with OpenAI
Responses, and add per-instance budgets, a browser-process watchdog and input-focus
validation before typing. No Browser Use Cloud service is used.

tests/test_upstream.py retains the applicable upstream offline regression tests,
adapted for the injected CDP callable and configuration names. Original demo-only
flight verification and Chat Completions helper tests are replaced by local browser
and OpenAI Responses tests. Other files are original MCP integration work.
