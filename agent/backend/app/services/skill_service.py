from __future__ import annotations

import sys
from pathlib import Path

from app.schemas.task import SkillRecord

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class SkillService:
    def __init__(self) -> None:
        self._enabled_overrides: dict[str, bool] = {}

    def _registry(self):
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from gitIssueAssitant.skills import SkillRegistry

        registry = SkillRegistry(WORKSPACE_ROOT / "gitIssueAssitant" / "skills")
        registry.load()
        return registry

    def list_skills(self) -> list[SkillRecord]:
        records: list[SkillRecord] = []
        for skill in self._registry().list_skills():
            records.append(
                SkillRecord(
                    name=skill.name,
                    description=skill.description,
                    allowed_tools=skill.allowed_tools,
                    priority_tools=skill.priority_tools,
                    body=skill.body,
                    enabled=self._enabled_overrides.get(skill.name, True),
                )
            )
        return records

    def default_enabled_names(self) -> list[str]:
        return [skill.name for skill in self.list_skills() if skill.enabled]

    def set_enabled(self, name: str, enabled: bool) -> SkillRecord | None:
        skills = {skill.name: skill for skill in self.list_skills()}
        if name not in skills:
            return None
        self._enabled_overrides[name] = enabled
        skill = skills[name]
        return skill.model_copy(update={"enabled": enabled})


skill_service = SkillService()
