from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from gitIssueAssitant.core.schemas.task import SkillCreateRequest, SkillRecord

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
BUILTIN_SKILL_NAMES = {"patch-review", "test-failure-fix"}
SKILLS_DIR = WORKSPACE_ROOT / "gitIssueAssitant" / "core" / "agent" / "skills"


class SkillService:
    def __init__(self) -> None:
        self._enabled_overrides: dict[str, bool] = {}

    def _registry(self):
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from gitIssueAssitant.core.agent.skills import SkillRegistry

        registry = SkillRegistry(SKILLS_DIR)
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
                    builtin=skill.name in BUILTIN_SKILL_NAMES,
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

    def create_skill(self, payload: SkillCreateRequest) -> SkillRecord:
        name = self._normalize_name(payload.name)
        if name in {skill.name for skill in self.list_skills()}:
            raise ValueError("Skill name already exists")

        skill_dir = SKILLS_DIR / name
        skill_dir.mkdir(parents=True, exist_ok=False)
        (skill_dir / "SKILL.md").write_text(
            self._format_skill_file(
                name=name,
                description=payload.description.strip(),
                allowed_tools=self._clean_tool_list(payload.allowed_tools),
                priority_tools=self._clean_tool_list(payload.priority_tools),
                body=payload.body.strip(),
            ),
            encoding="utf-8",
        )
        self._enabled_overrides[name] = payload.enabled
        skill = {skill.name: skill for skill in self.list_skills()}[name]
        return skill.model_copy(update={"enabled": payload.enabled})

    def delete_skill(self, name: str) -> bool | None:
        skills = {skill.name: skill for skill in self.list_skills()}
        if name not in skills:
            return None

        skill_dir = (SKILLS_DIR / name).resolve()
        skills_root = SKILLS_DIR.resolve()
        if not skill_dir.is_relative_to(skills_root) or skill_dir == skills_root:
            return False

        try:
            shutil.rmtree(skill_dir, onerror=self._handle_remove_error)
        except OSError as exc:
            raise ValueError(f"Skill could not be deleted: {exc}") from exc
        self._enabled_overrides.pop(name, None)
        return True

    def _normalize_name(self, name: str) -> str:
        normalized = name.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", normalized):
            raise ValueError("Skill name can only contain lowercase letters, numbers, hyphens, and underscores")
        return normalized

    def _clean_tool_list(self, tools: list[str]) -> list[str]:
        return [tool.strip() for tool in tools if tool.strip()]

    def _handle_remove_error(self, function, path: str, excinfo) -> None:
        Path(path).chmod(0o700)
        function(path)

    def _format_skill_file(
        self,
        *,
        name: str,
        description: str,
        allowed_tools: list[str],
        priority_tools: list[str],
        body: str,
    ) -> str:
        allowed = ", ".join(allowed_tools)
        priority = ", ".join(priority_tools)
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"allowed_tools: [{allowed}]\n"
            f"priority_tools: [{priority}]\n"
            "---\n\n"
            f"{body}\n"
        )


skill_service = SkillService()

