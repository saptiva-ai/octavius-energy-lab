"""
Services package for Copilot OS API.
"""


# Lazy import to avoid blocking startup if optional dependencies are missing
def __getattr__(name):
    if name == "email_service":
        from . import email_service

        return email_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["email_service"]
