"""Tests for the contact discovery agent config, launcher tool, and hook."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# agents/contact_discovery.py
# ---------------------------------------------------------------------------

class TestContactDiscoveryTools:
    def test_all_expected_tools_present(self):
        from src.agents.contact_discovery import CONTACT_DISCOVERY_TOOLS

        expected = [
            "lookup_hubspot_contacts",
            "query_knowledge_base",
            "search_linkedin",
            "search_exa_people",
            "scrape_epc_website",
            "search_osha",
            "web_search",
            "web_search_broad",
            "fetch_page",
            "save_contact",
            "classify_contact",
            "enrich_contact_email",
            "enrich_contact_phone",
        ]
        for tool in expected:
            assert tool in CONTACT_DISCOVERY_TOOLS, f"Missing tool: {tool}"

    def test_tool_list_is_not_empty(self):
        from src.agents.contact_discovery import CONTACT_DISCOVERY_TOOLS
        assert len(CONTACT_DISCOVERY_TOOLS) > 0


class TestBuildContactDiscoveryPrompt:
    def _entity(self, **kwargs):
        base = {"id": "abc-123", "name": "Sunsteel EPC"}
        base.update(kwargs)
        return base

    def _project(self, **kwargs):
        base = {"project_name": "Mojave Sun", "state": "CA", "mw_capacity": 150}
        base.update(kwargs)
        return base

    def test_interpolates_entity_name(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "Sunsteel EPC" in prompt

    def test_interpolates_project_name(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "Mojave Sun" in prompt

    def test_interpolates_project_state(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "CA" in prompt

    def test_interpolates_project_mw(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "150" in prompt

    def test_interpolates_entity_id(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "abc-123" in prompt

    def test_missing_entity_fields_dont_crash(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt({}, {})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_buyer_context(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "Civ Robotics" in prompt
        assert "50MW+" in prompt

    def test_prompt_contains_save_contact_instruction(self):
        from src.agents.contact_discovery import build_contact_discovery_prompt

        prompt = build_contact_discovery_prompt(self._entity(), self._project())
        assert "save_contact" in prompt


# ---------------------------------------------------------------------------
# tools/run_contact_discovery.py
# ---------------------------------------------------------------------------

class TestRunContactDiscoveryDefinition:
    def test_definition_name(self):
        from src.tools.run_contact_discovery import DEFINITION
        assert DEFINITION["name"] == "run_contact_discovery"

    def test_definition_has_required_fields(self):
        from src.tools.run_contact_discovery import DEFINITION
        schema = DEFINITION["input_schema"]
        assert "entity_id" in schema["properties"]
        assert "project_id" in schema["properties"]
        assert "entity_id" in schema["required"]
        assert "project_id" in schema["required"]


class TestRunContactDiscoveryInput:
    def test_valid_input(self):
        from src.tools.run_contact_discovery import Input
        inp = Input(entity_id="abc-123", project_id=42)
        assert inp.entity_id == "abc-123"
        assert inp.project_id == 42

    def test_missing_entity_id_raises(self):
        from pydantic import ValidationError
        from src.tools.run_contact_discovery import Input
        with pytest.raises(ValidationError):
            Input(project_id=42)

    def test_missing_project_id_raises(self):
        from pydantic import ValidationError
        from src.tools.run_contact_discovery import Input
        with pytest.raises(ValidationError):
            Input(entity_id="abc-123")

    def test_project_id_must_be_int(self):
        from pydantic import ValidationError
        from src.tools.run_contact_discovery import Input
        with pytest.raises(ValidationError):
            Input(entity_id="abc-123", project_id="not-an-int")


@pytest.mark.asyncio
class TestRunContactDiscoveryExecute:
    async def test_returns_success_status(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["status"] == "success"

    async def test_returns_source_field(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["source"] == "contact_discovery"

    async def test_returns_available_tools(self):
        from src.tools.run_contact_discovery import execute
        from src.agents.contact_discovery import CONTACT_DISCOVERY_TOOLS
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["data"]["available_tools"] == CONTACT_DISCOVERY_TOOLS

    async def test_echoes_entity_id(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["data"]["entity_id"] == "abc-123"

    async def test_echoes_project_id(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["data"]["project_id"] == 42

    async def test_mode_is_manual(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert result["data"]["mode"] == "manual"

    async def test_message_mentions_runtime_revamp(self):
        from src.tools.run_contact_discovery import execute
        result = await execute({"entity_id": "abc-123", "project_id": 42})
        assert "runtime revamp" in result["data"]["message"]


# ---------------------------------------------------------------------------
# hooks/contact_save.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestContactSaveHookPreTool:
    async def test_pre_tool_returns_continue(self):
        from src.hooks.contact_save import ContactSaveHook
        hook = ContactSaveHook()
        result = await hook.pre_tool("save_contact", {"entity_id": "x"}, {})
        assert result["action"] == "continue"

    async def test_pre_tool_passes_through_input(self):
        from src.hooks.contact_save import ContactSaveHook
        hook = ContactSaveHook()
        tool_input = {"entity_id": "x", "full_name": "Jane"}
        result = await hook.pre_tool("save_contact", tool_input, {})
        assert result["tool_input"] == tool_input

    async def test_pre_tool_noop_for_other_tools(self):
        from src.hooks.contact_save import ContactSaveHook
        hook = ContactSaveHook()
        tool_input = {"query": "something"}
        result = await hook.pre_tool("web_search", tool_input, {})
        assert result["action"] == "continue"
        assert result["tool_input"] == tool_input


@pytest.mark.asyncio
class TestContactSaveHookPostTool:
    async def test_noop_for_non_save_contact_tool(self):
        from src.hooks.contact_save import ContactSaveHook
        hook = ContactSaveHook()
        result = {"status": "success", "data": {}}
        returned = await hook.post_tool("web_search", {}, result, {})
        assert returned is result  # unchanged

    async def test_noop_when_result_not_success(self):
        from src.hooks.contact_save import ContactSaveHook
        hook = ContactSaveHook()
        result = {"status": "error", "message": "something broke"}
        returned = await hook.post_tool("save_contact", {"entity_id": "x"}, result, {})
        assert returned is result

    async def test_updates_entity_on_success(self):
        from src.hooks.contact_save import ContactSaveHook

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # get_client is imported lazily inside the method, so patch at src.db level
        with patch("src.db.get_client", return_value=mock_client):
            hook = ContactSaveHook()
            result = {"status": "success", "data": {"id": "contact-1"}}
            returned = await hook.post_tool(
                "save_contact", {"entity_id": "entity-abc"}, result, {}
            )

        mock_client.table.assert_called_once_with("entities")
        mock_table.update.assert_called_once_with({"contact_discovery_status": "in_progress"})
        mock_table.eq.assert_called_once_with("id", "entity-abc")
        mock_table.execute.assert_called_once()
        assert returned is result

    async def test_noop_when_no_entity_id(self):
        from src.hooks.contact_save import ContactSaveHook

        mock_client = MagicMock()
        with patch("src.db.get_client", return_value=mock_client):
            hook = ContactSaveHook()
            result = {"status": "success"}
            returned = await hook.post_tool("save_contact", {}, result, {})

        mock_client.table.assert_not_called()
        assert returned is result

    async def test_db_error_is_swallowed(self):
        from src.hooks.contact_save import ContactSaveHook

        mock_client = MagicMock()
        mock_client.table.side_effect = RuntimeError("DB down")

        with patch("src.db.get_client", return_value=mock_client):
            hook = ContactSaveHook()
            result = {"status": "success"}
            # Should not raise
            returned = await hook.post_tool(
                "save_contact", {"entity_id": "entity-abc"}, result, {}
            )

        assert returned is result
