"""Tests for the send_line_message / check_line_messages tools."""

from line_bot_mcp import server


def test_send_empty_rejected():
    assert server.send_line_message("") == "Error: text is empty"
    assert server.send_line_message("   ") == "Error: text is empty"


def test_send_too_long_rejected():
    result = server.send_line_message("あ" * (server.MAX_LEN + 1))
    assert result.startswith("Error: text too long")


def test_send_without_token_reports_error(monkeypatch):
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_KOUTA_USER_ID", raising=False)
    result = server.send_line_message("やあ")
    assert "not set" in result


def test_send_success_calls_push(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_KOUTA_USER_ID", "U1")
    captured = {}

    def fake_push(token, to, text):
        captured.update(token=token, to=to, text=text)

    monkeypatch.setattr(server.line_client, "push", fake_push)
    result = server.send_line_message("やあ")
    assert result == "sent (len=2)"
    assert captured == {"token": "tok", "to": "U1", "text": "やあ"}


def test_send_surfaces_push_failure(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_KOUTA_USER_ID", "U1")

    def boom(token, to, text):
        raise RuntimeError("429 too many")

    monkeypatch.setattr(server.line_client, "push", boom)
    result = server.send_line_message("hi")
    assert result == "Error: 429 too many"


def test_check_without_table(monkeypatch):
    monkeypatch.setenv("LINE_INBOX_TABLE", "")
    result = server.check_line_messages()
    assert "not set" in result
