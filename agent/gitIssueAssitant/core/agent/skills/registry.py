from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    priority_tools: list[str] = field(default_factory=list)
    body: str = ""

    def as_router_entry(self) -> str:
        return f"- {self.name}: {self.description}"


class SkillRegistry:
    """扫描 skills/ 目录，加载每个 Skill 的 frontmatter + 正文。

    SKILL.md 文件格式：
        ---
        name: skill-name
        description: 一句话说明何时使用
        allowed_tools: [tool_a, tool_b]
        priority_tools: [tool_a]
        ---

        # 正文 markdown ...
    """

    def __init__(self, skills_dir: Path | str | None = None):
        if skills_dir is None:
            skills_dir = Path(__file__).resolve().parent
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def load(self) -> dict[str, Skill]:
        self._skills = {}
        if not self.skills_dir.exists():
            self._loaded = True
            return self._skills

        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            skill = self._parse_skill_file(skill_md)
            if skill is not None:
                self._skills[skill.name] = skill
        self._loaded = True
        return self._skills

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def list_skills(self) -> list[Skill]:
        self._ensure_loaded()
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        self._ensure_loaded()
        return self._skills.get(name)

    def router_catalog(self) -> str:
        """给 LLM 看的 skills 列表，仅含 name + description。"""
        entries = [skill.as_router_entry() for skill in self.list_skills()]
        return "\n".join(entries) if entries else "(无可用 Skill)"

    def _parse_skill_file(self, path: Path) -> Skill | None:
        text = path.read_text(encoding="utf-8")
        meta, body = self._split_frontmatter(text)
        if meta is None:
            return None

        name = meta.get("name") or path.parent.name
        description = meta.get("description", "")
        allowed_tools = self._parse_list(meta.get("allowed_tools"))
        priority_tools = self._parse_list(meta.get("priority_tools"))

        return Skill(
            name=str(name).strip(),
            description=str(description).strip(),
            allowed_tools=allowed_tools,
            priority_tools=priority_tools,
            body=body.strip(),
        )

    def _split_frontmatter(self, text: str) -> tuple[dict[str, str] | None, str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None, text

        meta: dict[str, str] = {}
        idx = 1
        while idx < len(lines):
            line = lines[idx]
            if line.strip() == "---":
                body = "\n".join(lines[idx + 1 :])
                return meta, body
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
            idx += 1
        return None, text

    def _parse_list(self, raw: str | None) -> list[str]:
        if not raw:
            return []
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]

