import asyncio
import os

import pytest

from jev_ultrafast_mcp import server


@pytest.mark.parametrize("host_key", [None, "host-provided-key"])
def test_startup_uses_only_host_environment(monkeypatch, tmp_path, host_key):
    package = tmp_path / "jev_ultrafast_mcp"
    package.mkdir()
    (tmp_path / ".env").write_text(
        "TYPESAFE_API_KEY=file-key\nOPENAI_API_KEY=file-openai-key\nOPENAI_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "__file__", str(package / "server.py"))
    for name in ("TYPESAFE_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    if host_key is not None:
        monkeypatch.setenv("TYPESAFE_API_KEY", host_key)
        monkeypatch.setenv("OPENAI_API_KEY", host_key)
        monkeypatch.setenv("OPENAI_MODEL", "host-model")

    def run(*, transport):
        assert transport == "stdio"
        assert os.getenv("TYPESAFE_API_KEY") == host_key
        assert os.getenv("OPENAI_API_KEY") == host_key
        assert os.getenv("OPENAI_MODEL") == ("host-model" if host_key else None)

    monkeypatch.setattr(server.mcp, "run", run)
    server.main()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_typesafe_environment_has_clear_error(monkeypatch, key):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    if key is not None:
        monkeypatch.setenv("TYPESAFE_API_KEY", key)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        asyncio.run(server.browse("https://example.com", "Read the page"))
