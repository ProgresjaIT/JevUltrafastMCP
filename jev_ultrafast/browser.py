"""Upstream observed actions using an owned headless Playwright CDP session."""

import hashlib
import json
import sys
import time
from pathlib import Path
from threading import Timer

import psutil
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# Atomically read visible content and controls, preserving actual DOM node identity.
READ_STATE = Path(__file__).with_name("snapshot.js").read_text(encoding="utf-8")
MARKER = f"(() => {{ const state={READ_STATE}; return state?.marker ?? null; }})()"

class StalePage(ValueError):
    """A decision no longer refers to the observed page."""


class Browser:
    def __init__(self, url, *, timeout_seconds=120):
        self.playwright = None
        self.browser = None
        self.closed = False
        self.timed_out = False
        self.watchdog = None
        deadline = time.monotonic() + timeout_seconds
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True, timeout=30_000)
            browser_session = self.browser.new_browser_cdp_session()
            processes = browser_session.send("SystemInfo.getProcessInfo")["processInfo"]
            pid = next(p["id"] for p in processes if p["type"] == "browser")
            self.process = psutil.Process(pid)
            browser_session.detach()
            self.watchdog = Timer(max(0, deadline - time.monotonic()), self._expire)
            self.watchdog.daemon = True
            self.watchdog.start()
            self.context = self.browser.new_context(viewport={"width": 1120, "height": 780}, accept_downloads=False)
            self.page = self.context.new_page()
            self.session = self.context.new_cdp_session(self.page)
            self.call("Emulation.setFocusEmulationEnabled", enabled=True)
            self.page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        except BaseException:
            self.close()
            if self.timed_out:
                raise TimeoutError("Browser time budget exhausted during startup") from None
            raise

    def _expire(self):
        """Kill only this owned browser tree, even when the renderer/CDP is stuck."""
        if not self.process.is_running():
            return
        self.timed_out = True
        try:
            processes = [*reversed(self.process.children(recursive=True)), self.process]
        except psutil.NoSuchProcess:
            return
        for process in processes:
            try:
                process.kill()  # psutil checks creation time, protecting against PID reuse.
            except psutil.NoSuchProcess:
                pass

    def call(self, method, **params):
        try:
            return self.session.send(method, params)
        except PlaywrightError as exc:
            if method == "Runtime.evaluate" and any(message in str(exc) for message in (
                "Execution context was destroyed", "Cannot find context", "Inspected target navigated",
            )):
                return {"exceptionDetails": {"text": "Document changed"}}
            raise RuntimeError("Browser operation failed; execution may be incomplete.") from None

    def evaluate(self, expression):
        response = self.call("Runtime.evaluate", expression=expression, returnByValue=True)
        if response.get("exceptionDetails"):
            raise StalePage("Document changed during evaluation")
        return response.get("result", {}).get("value")

    def observe(self, screenshot=True):
        if getattr(self, "after_input", None):
            action, self.after_input = self.after_input, None
            # This is read-only and happens after execution was logged, even if navigation interrupts it.
            try:
                self.call(
                    "Runtime.evaluate",
                    expression="""(action => new Promise(resolve => {
                      const field=window.__jevFast?.nodes.get(action.node);
                      const autocomplete=action.kind==='fill' && field?.getAttribute('role')==='combobox';
                      let frames=0, stopped=false;
                      const finish=()=>{stopped=true;resolve()};
                      setTimeout(finish,autocomplete ? 200 : 50);
                      const ready=()=>{
                        if (stopped) return;
                        const ids=(field?.getAttribute('aria-controls')||field?.getAttribute('aria-owns')||'')
                          .split(/\\s+/).filter(Boolean);
                        const roots=ids.length ? ids.map(id=>document.getElementById(id)).filter(Boolean) : [document];
                        const options=roots.flatMap(root=>[...root.querySelectorAll('[role="option"]')]);
                        if (++frames>=2 && (!autocomplete || options.some(e=>{
                          const r=e.getBoundingClientRect();
                          return r.width && r.height && r.bottom>0 && r.top<innerHeight &&
                            e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
                        }))) finish();
                        else requestAnimationFrame(ready);
                      };
                      requestAnimationFrame(ready);
                    }))(""" + json.dumps(action) + ")",
                    awaitPromise=True,
                    returnByValue=True,
                )
            except RuntimeError:
                pass
        for attempt in range(10):
            try:
                return browser_operation(
                    {"operation": "observe", "screenshot": screenshot}, self.call
                )
            except StalePage:
                if attempt == 9:
                    raise
                time.sleep(0.02)
        raise StalePage("Page did not settle")

    def fresh(self, page, action=None):
        if action is not None and action["kind"] in {"click", "select"}:
            node = action["node"]
            if type(node) is not int:
                return False
            current = self.evaluate(
                "(() => { const c=window.__jevFast; "
                f"return c ? [c.pageKey(),c.guard(c.nodes.get({node}))] : null; }})()"
            )
            return current == [page["page_key"], page["guards"].get(str(node))]
        return self.evaluate(MARKER) == page["marker"]

    def act(self, action, page, text=None):
        if not self.fresh(page, action):
            raise StalePage("Page changed since this decision. Observe again.")
        if action["kind"] == "wait":
            time.sleep(0.1)
        result = browser_operation({"operation": "act", "action": action, "text": text}, self.call)
        self.after_input = action if action["kind"] != "wait" else None
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.browser is not None:
                self.browser.close()
        finally:
            try:
                if self.playwright is not None:
                    self.playwright.stop()
            finally:
                if self.watchdog is not None:
                    self.watchdog.cancel()
                    self.watchdog.join()


def fingerprint(state):
    content = {k: state[k] for k in ("url", "text", "actions", "scroll")}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def browser_operation(request, call):
    operation = request["operation"]

    def evaluate(expression):
        result = call("Runtime.evaluate", expression=expression, returnByValue=True)
        if result.get("exceptionDetails"):
            if operation == "act" and request["action"]["kind"] == "select":
                raise RuntimeError("Dropdown execution was interrupted; inspect before retrying.")
            raise StalePage("Document changed during evaluation")
        return result.get("result", {}).get("value")

    if operation == "act":
        action = request["action"]
        kind = action["kind"]
        if kind == "scroll":
            call("Input.dispatchMouseEvent", type="mouseWheel", x=550, y=650, deltaX=0, deltaY=action["delta"])
        elif kind != "wait":
            if type(action["node"]) is not int:
                raise ValueError("Invalid observed node")
            # Code-owned node IDs refer to actual observed elements, never model-generated selectors.
            target = evaluate("""(action => {
              const e=window.__jevFast?.nodes.get(action.node);
              if (!e?.isConnected || e.matches(':disabled') || e.closest('[aria-disabled="true"],[inert]') ||
                  !e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})) return null;
              if (action.kind==='fill' && (e.readOnly || e.getAttribute('aria-readonly')==='true')) return null;
              const r=e.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
              if (!r.width || !r.height || x<0 || y<0 || x>=innerWidth || y>=innerHeight) return null;
              if (!e.contains(document.elementFromPoint(x,y))) return null;
              if (action.kind==='select') {
                if (e.tagName!=='SELECT' || ![...e.options].some(o=>o.value===action.value &&
                    !o.disabled && !o.closest('optgroup[disabled]'))) return null;
                e.value=action.value;
                e.dispatchEvent(new Event('input',{bubbles:true}));
                e.dispatchEvent(new Event('change',{bubbles:true}));
              }
              return {x,y};
            })(""" + json.dumps(action) + ")")
            if target is None:
                if kind == "select":
                    raise RuntimeError("Dropdown execution was not confirmed; inspect before retrying.")
                raise StalePage("Target changed or is covered. Observe again.")
            if kind != "select":
                x, y = target["x"], target["y"]
                for event in ("mousePressed", "mouseReleased"):
                    call("Input.dispatchMouseEvent", type=event, x=x, y=y, button="left", clickCount=1)
                if kind == "fill":
                    def check_focus():
                        try:
                            focused = evaluate(
                                "(() => { const e=window.__jevFast?.nodes.get("
                                + str(action["node"])
                                + "); return !!e && e === document.activeElement; })()"
                            )
                        except StalePage:
                            # The click already happened. Never retry it after navigation.
                            raise RuntimeError("Page changed after focus click; inspect before retrying.") from None
                        if not focused:
                            raise RuntimeError(
                                "Input focus changed after click; nothing typed. Inspect before retrying."
                            )

                    check_focus()
                    call(
                        "Input.dispatchKeyEvent",
                        type="keyDown",
                        key="a",
                        code="KeyA",
                        modifiers=4 if sys.platform == "darwin" else 2,
                        commands=["selectAll"],
                    )
                    check_focus()
                    call(
                        "Input.dispatchKeyEvent",
                        type="keyUp",
                        key="a",
                        code="KeyA",
                        modifiers=4 if sys.platform == "darwin" else 2,
                    )
                    check_focus()
                    call("Input.insertText", text=request["text"])
        return {"executed": action["id"]}

    info = evaluate(READ_STATE)
    if info is None:
        raise StalePage("Document is navigating")
    info["fingerprint"] = fingerprint(info)
    if request.get("screenshot", True):
        info["screenshot"] = call("Page.captureScreenshot", format="jpeg", quality=72)["data"]
    return info
