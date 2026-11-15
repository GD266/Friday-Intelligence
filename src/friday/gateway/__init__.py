"""AI gateway for FRIDAY 2.0.

The gateway talks to OpenAI-compatible HTTP providers and streams typed
events. Provider failures are raised as :mod:`friday.gateway.errors`.
"""

from friday.gateway.base import Provider
from friday.gateway.errors import (
    AuthError,
    Cancelled,
    GatewayError,
    MalformedResponse,
    NetworkError,
    NotConfigured,
    NotFound,
    RateLimited,
    ServerError,
    TimeoutError,
)
from friday.gateway.types import ChatRequest, Message, StreamEvent, Usage

__all__ = [
    "AuthError",
    "Cancelled",
    "ChatRequest",
    "GatewayError",
    "MalformedResponse",
    "Message",
    "NetworkError",
    "NotConfigured",
    "NotFound",
    "Provider",
    "RateLimited",
    "ServerError",
    "StreamEvent",
    "TimeoutError",
    "Usage",
]
