"""Langfuse tracing for all LLM calls — scheduling agent, eval judge, simulated patient, improver."""
from langfuse import Langfuse
from app.config import settings

langfuse = Langfuse(
    secret_key=settings.langfuse_secret_key,
    public_key=settings.langfuse_public_key,
    host=settings.langfuse_host,
)


def start_trace(name: str, **kwargs):
    """Start a new trace (top-level observation) and return it."""
    return langfuse.start_as_current_observation(name=name, as_type="span", **kwargs)


def start_span(name: str, **kwargs):
    """Start a child span within the current trace context."""
    return langfuse.start_observation(name=name, as_type="span", **kwargs)


def start_generation(name: str, model: str = None, **kwargs):
    """Start a generation observation for an LLM call."""
    return langfuse.start_observation(name=name, as_type="generation", model=model, **kwargs)
