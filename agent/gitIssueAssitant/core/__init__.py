"""Shared core interfaces for the CLI and REST API adapters."""

__all__ = [
    "Agent",
    "AgentOrchestrator",
    "LLM_factory",
    "Session",
    "SessionService",
]


def __getattr__(name: str):
    if name in {"Agent", "LLM_factory"}:
        from .agent import Agent, LLM_factory

        return {"Agent": Agent, "LLM_factory": LLM_factory}[name]
    if name == "AgentOrchestrator":
        from .agent import AgentOrchestrator

        return AgentOrchestrator
    if name in {"Session", "SessionService"}:
        from .services.session_service import Session, SessionService

        return {"Session": Session, "SessionService": SessionService}[name]
    raise AttributeError(name)

