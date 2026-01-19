"""
Provider exceptions
"""


class ProviderError(Exception):
    """Base exception for provider errors"""
    pass


class RateLimitError(ProviderError):
    """Raised when rate limit is hit"""
    pass


class ParseError(ProviderError):
    """Raised when parsing fails"""
    pass


class NotSupportedError(ProviderError):
    """Raised when a provider doesn't support a requested operation"""
    pass
