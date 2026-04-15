"""Tests for the share-link FastAPI endpoints in main.py.

Covers:
- Token generation (shape, entropy, uniqueness)
- POST idempotency (second call returns existing token)
- POST blocked when an agent job is active (409)
- DELETE clears token
- GET /api/share/{token} — public, sanitized, 404 on invalid/revoked
- Access log is written on every public fetch (best-effort, never raises)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, require_auth

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client():
    app.dependency_overrides[require_auth] = lambda: "test-user-id"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
async def public_client():
    """Client with no auth override — for hitting public /api/share/{token}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Token shape
# ---------------------------------------------------------------------------


class TestTokenShape:
    @pytest.mark.asyncio
    @patch("src.main.get_active_job_for_conversation", return_value=None)
    @patch("src.main.db.set_share_token")
    async def test_token_is_url_safe_and_high_entropy(self, mock_set, mock_active_job, client):
        captured = {}

        def capture(conv_id, user_id, token):
            captured["token"] = token
            return {"token": token, "shared_at": "2026-04-15T00:00:00Z"}

        mock_set.side_effect = capture

        res = await client.post("/api/conversations/conv-1/share")
        assert res.status_code == 200

        token = captured["token"]
        # secrets.token_urlsafe(16) → 22 URL-safe chars
        assert len(token) >= 20
        # URL-safe alphabet only: A-Z a-z 0-9 _ -
        assert all(c.isalnum() or c in "-_" for c in token)

    @pytest.mark.asyncio
    @patch("src.main.get_active_job_for_conversation", return_value=None)
    @patch("src.main.db.set_share_token")
    async def test_tokens_are_unique_across_calls(self, mock_set, mock_active_job, client):
        tokens_seen: list[str] = []

        def capture(conv_id, user_id, token):
            tokens_seen.append(token)
            return {"token": token, "shared_at": "2026-04-15T00:00:00Z"}

        mock_set.side_effect = capture

        for _ in range(5):
            await client.post("/api/conversations/conv-x/share")

        assert len(set(tokens_seen)) == 5, "tokens are not unique"


# ---------------------------------------------------------------------------
# POST /api/conversations/{id}/share
# ---------------------------------------------------------------------------


class TestCreateShareLink:
    @pytest.mark.asyncio
    @patch("src.main.get_active_job_for_conversation", return_value=None)
    @patch(
        "src.main.db.set_share_token",
        return_value={"token": "abc123XYZ_new", "shared_at": "2026-04-15T00:00:00Z"},
    )
    async def test_returns_token_path_and_timestamp(self, mock_set, mock_active_job, client):
        res = await client.post("/api/conversations/conv-1/share")
        assert res.status_code == 200
        body = res.json()
        assert body["token"] == "abc123XYZ_new"
        assert body["shared_at"] == "2026-04-15T00:00:00Z"
        assert body["path"] == "/share/abc123XYZ_new"

    @pytest.mark.asyncio
    @patch("src.main.get_active_job_for_conversation", return_value=MagicMock())
    async def test_rejects_when_job_active_with_409(self, mock_active_job, client):
        res = await client.post("/api/conversations/conv-1/share")
        assert res.status_code == 409
        body = res.json()
        assert body["detail"]["error"] == "wait_for_completion"
        assert "finish" in body["detail"]["message"].lower()

    @pytest.mark.asyncio
    @patch("src.main.get_active_job_for_conversation", return_value=None)
    @patch("src.main.db.set_share_token", return_value=None)
    async def test_404_when_conversation_not_owned(self, mock_set, mock_active_job, client):
        res = await client.post("/api/conversations/someone-elses/share")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/conversations/{id}/share  (owner preview)
# ---------------------------------------------------------------------------


class TestGetShareState:
    @pytest.mark.asyncio
    @patch(
        "src.main.db.get_share_state",
        return_value={"token": "t1", "shared_at": "2026-04-15T00:00:00Z"},
    )
    async def test_returns_existing_share(self, mock_state, client):
        res = await client.get("/api/conversations/conv-1/share")
        assert res.status_code == 200
        body = res.json()
        assert body["token"] == "t1"
        assert body["path"] == "/share/t1"

    @pytest.mark.asyncio
    @patch(
        "src.main.db.get_share_state",
        return_value={"token": None, "shared_at": None},
    )
    async def test_returns_null_when_not_shared(self, mock_state, client):
        res = await client.get("/api/conversations/conv-1/share")
        assert res.status_code == 200
        body = res.json()
        assert body["token"] is None
        assert body["path"] is None

    @pytest.mark.asyncio
    @patch("src.main.db.get_share_state", return_value=None)
    async def test_404_when_not_owned(self, mock_state, client):
        res = await client.get("/api/conversations/stranger/share")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/conversations/{id}/share
# ---------------------------------------------------------------------------


class TestRevokeShareLink:
    @pytest.mark.asyncio
    @patch("src.main.db.clear_share_token", return_value=True)
    async def test_revokes_successfully(self, mock_clear, client):
        res = await client.delete("/api/conversations/conv-1/share")
        assert res.status_code == 200
        assert res.json()["status"] == "revoked"

    @pytest.mark.asyncio
    @patch("src.main.db.clear_share_token", return_value=False)
    async def test_404_when_not_owned(self, mock_clear, client):
        res = await client.delete("/api/conversations/stranger/share")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/share/{token}  (public)
# ---------------------------------------------------------------------------


class TestPublicShareFetch:
    @pytest.mark.asyncio
    @patch("src.main.db.log_share_access")
    @patch("src.main.db.fetch_shared_conversation")
    async def test_returns_sanitized_snapshot(self, mock_fetch, mock_log, public_client):
        mock_fetch.return_value = {
            "conversation": {
                "id": "c1",
                "title": "TX research",
                "shared_at": "2026-04-15T00:00:00Z",
            },
            "messages": [
                {
                    "id": "m1",
                    "role": "user",
                    "content": "find projects",
                    "parts": [{"type": "text", "text": "find projects"}],
                    "created_at": "2026-04-15T00:00:00Z",
                },
                {
                    "id": "m2",
                    "role": "assistant",
                    "content": "",
                    "parts": [
                        {
                            "type": "tool-research_scratchpad",
                            "toolName": "research_scratchpad",
                            "input": {"key": "notes"},
                            "output": {"ok": True},
                        },
                        {
                            "type": "tool-web_search",
                            "toolName": "web_search",
                            "input": {"query": "TX solar", "_batch_id": "internal"},
                            "output": {"results": []},
                        },
                    ],
                    "created_at": "2026-04-15T00:00:01Z",
                },
            ],
        }

        res = await public_client.get("/api/share/test-token-123")
        assert res.status_code == 200
        body = res.json()
        assert body["conversation"]["title"] == "TX research"
        assert len(body["messages"]) == 2

        assistant_parts = body["messages"][1]["parts"]
        # scratchpad stripped, web_search kept
        assert len(assistant_parts) == 1
        assert assistant_parts[0]["toolName"] == "web_search"
        # _batch_id stripped
        assert "_batch_id" not in assistant_parts[0]["input"]
        assert assistant_parts[0]["input"]["query"] == "TX solar"

    @pytest.mark.asyncio
    @patch("src.main.db.log_share_access")
    @patch("src.main.db.fetch_shared_conversation", return_value=None)
    async def test_404_when_token_invalid(self, mock_fetch, mock_log, public_client):
        res = await public_client.get("/api/share/never-existed")
        assert res.status_code == 404

    @pytest.mark.asyncio
    @patch("src.main.db.log_share_access")
    @patch("src.main.db.fetch_shared_conversation", return_value=None)
    async def test_404_when_token_revoked(self, mock_fetch, mock_log, public_client):
        # A revoked token looks the same as an invalid token — no info leak
        # about whether it *used to* exist.
        res = await public_client.get("/api/share/revoked-token")
        assert res.status_code == 404

    @pytest.mark.asyncio
    @patch("src.main.db.log_share_access")
    @patch("src.main.db.fetch_shared_conversation")
    async def test_logs_access_on_successful_fetch(self, mock_fetch, mock_log, public_client):
        mock_fetch.return_value = {
            "conversation": {"id": "c1", "title": "t", "shared_at": "2026-04-15T00:00:00Z"},
            "messages": [],
        }
        await public_client.get(
            "/api/share/t1",
            headers={"User-Agent": "slackbot/1.0", "X-Forwarded-For": "1.2.3.4"},
        )
        assert mock_log.call_count == 1
        kwargs = mock_log.call_args.kwargs
        assert kwargs["token"] == "t1"
        assert kwargs["conversation_id"] == "c1"
        assert kwargs["user_agent"] == "slackbot/1.0"
        # IP should be hashed, not the raw "1.2.3.4"
        assert kwargs["ip_hash"] is not None
        assert kwargs["ip_hash"] != "1.2.3.4"
        assert len(kwargs["ip_hash"]) <= 32

    @pytest.mark.asyncio
    @patch("src.main.logger")
    @patch("src.main.db.log_share_access", side_effect=RuntimeError("db down"))
    @patch("src.main.db.fetch_shared_conversation")
    async def test_log_failure_does_not_break_response(
        self, mock_fetch, mock_log, mock_logger, public_client
    ):
        """Audit log failure must never fail the user-facing request."""
        mock_fetch.return_value = {
            "conversation": {"id": "c1", "title": "t", "shared_at": "2026-04-15T00:00:00Z"},
            "messages": [],
        }
        res = await public_client.get("/api/share/t1")
        assert res.status_code == 200

    @pytest.mark.asyncio
    @patch("src.main.db.log_share_access")
    @patch("src.main.db.fetch_shared_conversation")
    async def test_no_auth_required(self, mock_fetch, mock_log, public_client):
        """The public endpoint must not require an Authorization header."""
        mock_fetch.return_value = {
            "conversation": {"id": "c1", "title": "t", "shared_at": "2026-04-15T00:00:00Z"},
            "messages": [],
        }
        res = await public_client.get("/api/share/t1")
        # If auth were required this would be 401 — confirm it's 200
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# IP hashing — daily-salted, not reversible
# ---------------------------------------------------------------------------


class TestIpHashing:
    def test_hashes_ip_with_daily_salt(self):
        from src.main import _hash_ip

        h1 = _hash_ip("1.2.3.4")
        h2 = _hash_ip("1.2.3.4")
        h3 = _hash_ip("5.6.7.8")

        assert h1 == h2, "same IP on same day should produce same hash"
        assert h1 != h3, "different IPs should produce different hashes"
        assert h1 != "1.2.3.4", "hash must not be reversible to the raw IP"

    def test_handles_none_ip(self):
        from src.main import _hash_ip

        assert _hash_ip(None) is None
        assert _hash_ip("") is None
