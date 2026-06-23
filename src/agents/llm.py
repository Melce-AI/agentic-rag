"""Single entry point for the chat model used by every LangGraph node.

Provider-agnostic by design: ``init_chat_model`` reads the ``provider:model``
string from settings (``AGENT_MODEL``) and builds the matching LangChain chat
model, importing the provider package lazily. Swapping providers — free local
Ollama, Anthropic, OpenAI — is therefore a config change, never a code change.

This is the project's one "model swap point" (see docs/architecture.md §3): the
nodes import ``get_chat_model()`` and never construct a model themselves.
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.core.config import get_settings


@lru_cache
def get_chat_model() -> BaseChatModel:
    """Return the shared chat model selected by ``settings.agent_model``.

    Cached: the model object is reusable and stateless across invocations, so
    we build it once. Binding tools (``model.bind_tools(...)``) returns a new
    runnable without mutating this one, so sharing it between nodes is safe.
    """
    settings = get_settings()
    kwargs: dict = {"temperature": settings.agent_temperature}
    # OpenAI-compatible gateways (e.g. OpenRouter) need an explicit base_url and
    # key. init_chat_model forwards extra kwargs to the provider constructor, so
    # we inject them only when a gateway URL is configured — the local/ollama
    # path stays untouched.
    if settings.agent_base_url:
        kwargs["base_url"] = settings.agent_base_url
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key.get_secret_value()
    return init_chat_model(settings.agent_model, **kwargs)
