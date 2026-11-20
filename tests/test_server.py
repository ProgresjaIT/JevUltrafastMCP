import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jev_ultrafast import model
from jev_ultrafast_mcp.server import browse


@pytest.fixture
def local_page():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            content = b'''<title>Local form</title><label>City<input id="city"></label>
            <button onclick="document.getElementById('result').textContent=
            'Saved '+document.getElementById('city').value">Save</button>
            <p id="result"></p>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def answer(options, selected):
    return {"choice": selected, "confidence": 1.0, "probabilities": {k: float(k == selected) for k in options}}


def test_browse_completes_actual_headless_form(monkeypatch, local_page):
    calls = []

    def provider(url, key, body):
        assert url == "https://api.typesafe.ai/v1/systemone"
        questions = body["questions"]
        state = body["state"]
        if "Saved Warsaw" in state["page"]["text"]:
            operation = "DONE"
        elif any(e.get("value") == "Warsaw" for e in state["elements"]):
            operation = "CLICK"
        else:
            operation = "TYPE_TEXT"
        calls.append(operation)
        answers = {"operation": answer(questions["operation"]["criteria"], operation)}
        if operation in {"CLICK", "TYPE_TEXT"}:
            head = operation.lower() + "_target"
            options = questions[head]["criteria"]
            selected = next(k for k, v in options.items() if operation == "TYPE_TEXT" or "Save" in v["element"])
            answers[head] = answer(options, selected)
        return {"model": "jev-test", "answers": answers, "usage": {}}

    # Keep the real DOM, policy validation, agent loop, and executor. Only network models are replaced.
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", provider)
    monkeypatch.setattr("jev_ultrafast.agent.field_text", lambda context: (
        "Warsaw", {"model": "gpt-6-luna", "latency_ms": 0, "usage": {}},
    ))
    result = asyncio.run(browse(local_page, "Enter Warsaw and click Save", max_steps=5))
    assert result["status"] == "done"
    assert "Saved Warsaw" in result["text"]
    assert result["verified"] is False
    assert result["url"].startswith(local_page)
    assert [h["kind"] for h in result["history"]] == ["fill", "click"]
    assert calls == ["TYPE_TEXT", "CLICK", "DONE"]
    json.dumps(result)


def test_wait_is_bounded(monkeypatch, local_page):
    def provider(url, key, body):
        return {"model": "test", "answers": {
            "operation": answer(body["questions"]["operation"]["criteria"], "WAIT"),
        }}

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", provider)
    result = asyncio.run(browse(local_page, "Wait forever", max_steps=2))
    assert result["status"] == "step_limit"
    assert len(result["history"]) == 2


def test_invalid_input_never_starts_browser():
    with pytest.raises(ValueError, match="HTTP"):
        asyncio.run(browse("file:///secret", "Read"))
    with pytest.raises(ValueError, match="goal"):
        asyncio.run(browse("https://example.com", " "))


def test_provider_failure_closes_browser_and_redacts_details(monkeypatch, local_page):
    from jev_ultrafast import agent

    browsers = []
    original = agent.Browser

    def tracked(url, **kwargs):
        browser = original(url, **kwargs)
        browsers.append(browser)
        return browser

    def failed(*args):
        raise RuntimeError("secret-api-key")

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(agent, "Browser", tracked)
    monkeypatch.setattr(model, "post_json", failed)
    result = asyncio.run(browse(local_page, "Search"))
    assert result["status"] == "error"
    assert "secret-api-key" not in json.dumps(result)
    assert browsers[0].closed
    assert not browsers[0].browser.is_connected()
