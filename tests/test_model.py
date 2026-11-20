import json

import httpx
import pytest
from openai import OpenAI

from jev_ultrafast import model


@pytest.mark.parametrize("value", ["Warsaw", None, "", "x" * 2001, 123, {"code": "no"}])
def test_openai_helper_validates_text_and_uses_luna(monkeypatch, value):
    def respond(request):
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["model"] == "gpt-6-luna"
        assert body["text"]["format"]["type"] == "json_schema"
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "gpt-6-luna", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": json.dumps({"text": value}), "annotations": []}]}],
            "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
        })

    client = OpenAI(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(model, "OpenAI", lambda **kwargs: client, raising=False)
    if value == "Warsaw":
        text, metadata = model.field_text({"goal": "Search for Warsaw"})
        assert text == "Warsaw"
        assert metadata["model"] == "gpt-6-luna"
    else:
        with pytest.raises(ValueError, match="valid field value"):
            model.field_text({"goal": "Search"})
