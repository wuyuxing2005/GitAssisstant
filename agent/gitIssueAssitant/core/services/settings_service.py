from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values

from gitIssueAssitant.core.schemas.settings import AppSettingsResponse, AppSettingsUpdate, ModelListResponse

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = WORKSPACE_ROOT / ".env"
DEFAULT_CLONE_ROOT = WORKSPACE_ROOT / "repos"

SETTING_KEYS = {
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "OPENAI_BASE_URL",
    "MODEL_NAME",
    "GIT_ISSUE_ASSISTANT_CLONE_ROOT",
}


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    return key.strip(), value.strip().strip('"').strip("'")


def _read_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for key, value in dotenv_values(ENV_FILE).items():
            if key and value is not None:
                values[key] = value

    for key in SETTING_KEYS:
        if os.getenv(key):
            values.setdefault(key, os.getenv(key, ""))
    return values


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_env_values(updates: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        parsed = _parse_env_line(line)
        if not parsed:
            output.append(line)
            continue

        key, _value = parsed
        if key in updates:
            output.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={_quote_env_value(value)}")

    ENV_FILE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _normalize_clone_root(value: str) -> str:
    raw = _repair_windows_path_escapes(value.strip())
    if not raw:
        return str(DEFAULT_CLONE_ROOT)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (WORKSPACE_ROOT / path).resolve()
    return str(path)


def _repair_windows_path_escapes(value: str) -> str:
    if os.name != "nt":
        return value
    return (
        value
        .replace("\r", r"\r")
        .replace("\n", r"\n")
        .replace("\t", r"\t")
    )


class SettingsService:
    def get_settings(self) -> AppSettingsResponse:
        values = _read_env_values()
        clone_root = _normalize_clone_root(values.get("GIT_ISSUE_ASSISTANT_CLONE_ROOT", ""))
        return AppSettingsResponse(
            openai_api_key_set=bool(values.get("OPENAI_API_KEY")),
            github_token_set=bool(values.get("GITHUB_TOKEN")),
            openai_api_key=values.get("OPENAI_API_KEY", ""),
            github_token=values.get("GITHUB_TOKEN", ""),
            openai_base_url=values.get("OPENAI_BASE_URL", ""),
            model_name=values.get("MODEL_NAME", ""),
            clone_root=clone_root,
            env_path=str(ENV_FILE),
        )

    def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsResponse:
        updates: dict[str, str] = {}
        if payload.openai_api_key is not None and payload.openai_api_key.strip():
            updates["OPENAI_API_KEY"] = payload.openai_api_key.strip()
        if payload.github_token is not None and payload.github_token.strip():
            updates["GITHUB_TOKEN"] = payload.github_token.strip()
        if payload.openai_base_url is not None:
            updates["OPENAI_BASE_URL"] = payload.openai_base_url.strip()
        if payload.model_name is not None:
            updates["MODEL_NAME"] = payload.model_name.strip()
        if payload.clone_root is not None:
            updates["GIT_ISSUE_ASSISTANT_CLONE_ROOT"] = _normalize_clone_root(payload.clone_root)

        if updates:
            _write_env_values(updates)
            for key, value in updates.items():
                if value:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
            if clone_root := updates.get("GIT_ISSUE_ASSISTANT_CLONE_ROOT"):
                Path(clone_root).mkdir(parents=True, exist_ok=True)

        return self.get_settings()

    def list_models(self) -> ModelListResponse:
        values = _read_env_values()
        api_key = values.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("请先在设置中填写 OPENAI_API_KEY")

        base_url = values.get("OPENAI_BASE_URL", "").rstrip("/") or "https://api.openai.com/v1"
        request = Request(
            f"{base_url}/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"模型列表获取失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"模型列表获取失败: {exc.reason}") from exc

        model_ids = sorted(
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        return ModelListResponse(models=model_ids)


settings_service = SettingsService()

