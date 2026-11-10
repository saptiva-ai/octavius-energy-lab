"""
Email normalization and validation utilities.

Provides canonical email handling to prevent authentication issues
caused by case sensitivity, whitespace, and common user input errors.
"""

import re
from typing import Optional


def normalize_email(email: str) -> str:
    """
    Canonicalize an email address for consistent storage and lookup.

    Transformations:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase (RFC 5321 local-part is case-sensitive,
       but most providers treat it as case-insensitive)
    3. Remove multiple consecutive dots in local-part (common typo)
    4. Validate basic structure

    Args:
        email: Raw email address string

    Returns:
        Normalized email address

    Raises:
        ValueError: If email format is invalid

    Examples:
        >>> normalize_email("  Test4@Saptiva.COM  ")
        'test4@saptiva.com'
        >>> normalize_email("user..name@example.com")
        'user.name@example.com'
        >>> normalize_email("USER@DOMAIN.COM")
        'user@domain.com'
    """
    if not email or not isinstance(email, str):
        raise ValueError("Email must be a non-empty string")

    # Step 1: Strip whitespace
    normalized = email.strip()

    # Step 2: Basic validation before processing
    if "@" not in normalized:
        raise ValueError("Invalid email format: missing @ symbol")

    # Step 3: Split into local and domain parts
    try:
        local_part, domain = normalized.rsplit("@", 1)
    except ValueError:
        raise ValueError("Invalid email format: malformed address")

    if not local_part or not domain:
        raise ValueError("Invalid email format: empty local or domain part")

    # Step 4: Normalize local part (remove consecutive dots)
    # Note: Some edge cases like leading/trailing dots are handled by EmailStr validator
    local_normalized = re.sub(r"\.{2,}", ".", local_part)

    # Step 5: Convert to lowercase (de-facto standard, though technically local-part is case-sensitive)
    local_normalized = local_normalized.lower()
    domain_normalized = domain.lower()

    # Step 6: Reconstruct
    result = f"{local_normalized}@{domain_normalized}"

    return result


def is_valid_email_format(email: str) -> bool:
    """
    Validate email format using a permissive regex.

    This is a basic check - full validation is done by Pydantic's EmailStr.

    Args:
        email: Email address to validate

    Returns:
        True if format is valid, False otherwise

    Examples:
        >>> is_valid_email_format("user@example.com")
        True
        >>> is_valid_email_format("invalid.email")
        False
        >>> is_valid_email_format("user@")
        False
    """
    # Permissive pattern that catches most common cases
    # Full RFC 5322 validation is handled by Pydantic EmailStr
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_email_for_lookup(identifier: str) -> str:
    """
    Sanitize an identifier for user lookup (username or email).

    If the identifier looks like an email, normalize it.
    Otherwise, just strip whitespace and lowercase (for username consistency).

    Args:
        identifier: Username or email address

    Returns:
        Sanitized identifier

    Examples:
        >>> sanitize_email_for_lookup("  Test4@Saptiva.COM  ")
        'test4@saptiva.com'
        >>> sanitize_email_for_lookup("  JohnDoe123  ")
        'johndoe123'
    """
    identifier = identifier.strip()

    # If it contains @, treat as email
    if "@" in identifier:
        try:
            return normalize_email(identifier)
        except ValueError:
            # If normalization fails, return lowercased stripped version
            return identifier.lower()

    # For usernames, just lowercase and strip
    return identifier.lower()


def get_email_validation_error(email: str) -> Optional[str]:
    """
    Get a human-readable validation error for an email address.

    Args:
        email: Email address to validate

    Returns:
        Error message if invalid, None if valid

    Examples:
        >>> get_email_validation_error("valid@example.com")
        None
        >>> get_email_validation_error("invalid.email")
        'El correo debe contener un símbolo @'
    """
    if not email or not isinstance(email, str):
        return "El correo electrónico es requerido"

    email = email.strip()

    if not email:
        return "El correo electrónico es requerido"

    if "@" not in email:
        return "El correo debe contener un símbolo @"

    if email.count("@") > 1:
        return "El correo solo puede contener un símbolo @"

    local, domain = email.rsplit("@", 1)

    if not local:
        return "El correo debe tener una parte antes del @"

    if not domain:
        return "El correo debe tener un dominio después del @"

    if "." not in domain:
        return "El dominio debe contener al menos un punto (.com, .org, etc.)"

    if domain.startswith(".") or domain.endswith("."):
        return "El dominio no puede empezar o terminar con un punto"

    if ".." in email:
        return "El correo no puede contener puntos consecutivos"

    # Basic character validation
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return "El correo contiene caracteres no válidos"

    return None
