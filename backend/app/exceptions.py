"""Domain exceptions for service layer; API maps these to HTTP responses."""


class ServiceError(Exception):
    """Base for service-layer errors (LLM, embedding, retrieval)."""


class LLMUnavailableError(ServiceError):
    """Raised when the LLM (e.g. LM Studio) is unreachable or fails."""
