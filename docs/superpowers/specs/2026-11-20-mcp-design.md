# Jev Ultrafast MCP — approved design

Python MCP server exposing `browse(url, goal, max_steps)` over stdio. Preserve
browser-use/jev-ultrafast's indexed DOM, operation/target decision loop and stale
page guards. TypeSafe Jev chooses actions; OpenAI gpt-6-luna supplies TYPE_TEXT
values only. Playwright owns an isolated headless Chromium process per call.
Return status, final URL, visible text and executed action history. Always clean up.

## Approaches
The initially proposed generic model router was rejected. The user selected the
original jev-ultrafast browser agent, Python and headless operation. Adapt its
small MIT-licensed core rather than replace it with the newer Browser Use agent.
Vendor the core at a recorded revision; replace Browser Harness transport with
Playwright CDP and the text helper with OpenAI Responses structured outputs.

## Constraints
No commits or pushes. Credentials only in environment/.env. No paid API calls in
tests. DONE is an agent claim, not independent verification. No persistent user
browser profile, HTTP service, arbitrary model-generated selectors or JavaScript.
Retain upstream limitations around frames, shadow DOM and new tabs.

## Builder choices
Python 3.12+, official MCP SDK FastMCP, per-call browser isolation, 60-step default,
bounded task duration checked between decisions and bounded provider requests.
Failed runs return a partial trace without blindly retrying browser mutations.
