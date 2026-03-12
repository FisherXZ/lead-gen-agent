"""Tests for the skills auto-discovery registry."""

from src.skills import get_skill, list_skills


class TestSkillsRegistry:
    def test_pdf_skill_discovered(self):
        skill = get_skill("pdf")
        assert skill is not None

    def test_pdf_skill_meta(self):
        skill = get_skill("pdf")
        assert skill.SKILL_META["name"] == "pdf"
        assert "version" in skill.SKILL_META

    def test_list_skills_includes_pdf(self):
        skills = list_skills()
        names = [s["name"] for s in skills]
        assert "pdf" in names

    def test_unknown_skill_returns_none(self):
        assert get_skill("nonexistent_skill") is None

    def test_pdf_skill_has_extract_functions(self):
        skill = get_skill("pdf")
        assert hasattr(skill, "extract_text")
        assert hasattr(skill, "extract_text_from_url")
