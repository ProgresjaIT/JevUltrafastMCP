import pytest

from jev_ultrafast.browser import Browser, StalePage


def test_headless_browser_fills_observed_node_and_rejects_stale_page():
    browser = Browser("about:blank")
    try:
        browser.evaluate('document.body.innerHTML = `<label>Name<input id="name"></label><button>Go</button>`')
        page = browser.observe(screenshot=False)
        field = next(a for a in page["actions"] if a["kind"] == "fill")
        browser.act(field, page, text="Ada")
        assert browser.evaluate('document.getElementById("name").value') == "Ada"
        with pytest.raises(StalePage):
            browser.act(field, page, text="Wrong")
        assert browser.evaluate('document.getElementById("name").value') == "Ada"
        assert "HeadlessChrome" in browser.evaluate("navigator.userAgent")
    finally:
        browser.close()
    assert not browser.browser.is_connected()


def test_browser_sessions_do_not_share_cookies():
    first = Browser("about:blank")
    try:
        first.context.add_cookies([{"name": "private", "value": "one", "url": "https://example.com"}])
    finally:
        first.close()
    second = Browser("about:blank")
    try:
        assert second.context.cookies() == []
    finally:
        second.close()


def test_failed_navigation_closes_browser(monkeypatch):
    from playwright.sync_api import BrowserType, Error

    launched = []
    original = BrowserType.launch

    def tracked(self, *args, **kwargs):
        instance = original(self, *args, **kwargs)
        launched.append(instance)
        return instance

    monkeypatch.setattr(BrowserType, "launch", tracked)
    with pytest.raises(Error):
        Browser("http://127.0.0.1:1")
    assert len(launched) == 1
    assert not launched[0].is_connected()


def test_text_entry_does_not_overwrite_redirected_focus():
    browser = Browser("about:blank")
    try:
        browser.evaluate('''document.body.innerHTML = `
        <label>Target<input id="target" onclick="document.getElementById('other').focus()"></label>
        <label>Other<input id="other" value="keep me"></label>`''')
        page = browser.observe(screenshot=False)
        target = next(a for a in page["actions"] if a["kind"] == "fill" and "Target" in a["label"])
        with pytest.raises(RuntimeError, match="focus"):
            browser.act(target, page, text="secret")
        assert browser.evaluate('document.getElementById("other").value') == "keep me"
        assert browser.evaluate('document.getElementById("target").value') == ""
    finally:
        browser.close()


def test_watchdog_terminates_hung_renderer():
    import time

    browser = Browser("about:blank", timeout_seconds=3)
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError):
            browser.evaluate("while (true) {}")
        assert browser.timed_out
        assert time.monotonic() - started < 10
    finally:
        browser.close()
    assert not browser.browser.is_connected()
