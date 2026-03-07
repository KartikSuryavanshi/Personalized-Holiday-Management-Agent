from autogen_ext.models.openai import OpenAIChatCompletionClient

from app.config import Settings


def build_model_client(settings: Settings) -> OpenAIChatCompletionClient:
    """Build an OpenAI-compatible model client (Ollama by default)."""

    return OpenAIChatCompletionClient(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "structured_output": True,
            "family": "unknown",
        },
    )
