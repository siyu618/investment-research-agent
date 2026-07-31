# Skills Registry — Central catalog of investment analysis skills

from pathlib import Path

import yaml

from strategies.base.models import StrategyCategory


class SkillRegistry:
    """Registry of all available investment analysis skills.

    Reads from registry/skills.yaml for metadata, and can load
    skill implementations dynamically by module path.
    """

    def __init__(self, registry_path: str = "registry/skills.yaml"):
        self.registry_path = Path(registry_path)
        self._skills: dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load skills from registry YAML."""
        if self.registry_path.exists():
            with open(self.registry_path) as f:
                data = yaml.safe_load(f)
                self._skills = data.get("skills", {})

    def list_skills(self) -> list[dict]:
        """List all registered skills with metadata."""
        return list(self._skills.values())

    def get_skill(self, name: str) -> dict | None:
        """Get skill metadata by name."""
        return self._skills.get(name)

    def get_skills_by_category(self, category: StrategyCategory) -> list[dict]:
        """Get all skills matching a category."""
        return [
            s for s in self._skills.values()
            if s.get("category") == category.value
        ]

    def get_analysis_skills(self) -> list[dict]:
        """Get all core analysis skills (not orchestration)."""
        return [
            s for s in self._skills.values()
            if s.get("category") != "orchestration"
        ]

    @property
    def count(self) -> int:
        return len(self._skills)
