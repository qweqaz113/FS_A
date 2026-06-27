from typing import Any

from enterprise_agent.agents.backends.sandbox import build_sandbox_backend
from enterprise_agent.agents.prompts import load_prompt
from enterprise_agent.agents.subagents.decompiler_noise_analyst import (
    build_decompiler_noise_analyst_subagent,
)
from enterprise_agent.agents.subagents.difference_analyst import build_difference_analyst_subagent
from enterprise_agent.agents.subagents.semantic_analyst import build_semantic_analyst_subagent
from enterprise_agent.agents.tools.registry import build_tools
from enterprise_agent.infra.config import get_settings


from deepagents import create_deep_agent


def create_enterprise_agent() -> Any:
    """Create the DeepAgents supervisor.

    The import is intentionally local so the rest of the project can be inspected
    before dependencies are installed.
    """
    settings = get_settings()
    sandbox_backend = build_sandbox_backend(settings)
    return create_deep_agent(
        tools=build_tools(),
        system_prompt=load_prompt("supervisor.md"),
        model=settings.llm_model,
        backend=sandbox_backend,
        subagents=[
            build_semantic_analyst_subagent(),
            build_difference_analyst_subagent(),
            build_decompiler_noise_analyst_subagent(),
        ],
        skills=[settings.sandbox_skills_dir],
    )


def create_function_similarity_error_analysis_agent() -> Any:
    """Create an agent that turns misclassified comparison traces into lessons."""

    settings = get_settings()
    sandbox_backend = build_sandbox_backend(settings)
    return create_deep_agent(
        tools=[],
        system_prompt=load_prompt("function_similarity_error_analysis.md"),
        model=settings.llm_model,
        backend=sandbox_backend,
        subagents=[],
        skills=[settings.sandbox_skills_dir],
    )


def create_function_similarity_package_materializer_agent() -> Any:
    """Create an agent that materializes an improved package in the sandbox."""

    settings = get_settings()
    sandbox_backend = build_sandbox_backend(settings)
    return create_deep_agent(
        tools=[],
        system_prompt=load_prompt("function_similarity_package_materializer.md"),
        model=settings.llm_model,
        backend=sandbox_backend,
        subagents=[],
        skills=[settings.sandbox_skills_dir],
    )
