"""
Comprehensive tests for core/crypto.py - Encryption/decryption utilities

Coverage:
- encrypt_secret: Symmetric encryption with Fernet
- decrypt_secret: Symmetric decryption with error handling
- Key derivation: Stable key generation from secrets
- Security: Invalid token handling, key consistency
"""

import pytest
from src.core.crypto import encrypt_secret, decrypt_secret, _derive_key, _get_cipher


class TestKeyDerivation:
    """Test stable key derivation from secrets."""

    def test_derive_key_deterministic(self):
        """Key derivation should be deterministic for the same secret."""
        secret = "my-secret-key"
        key1 = _derive_key(secret)
        key2 = _derive_key(secret)

        assert key1 == key2
        assert len(key1) == 44  # Base64-encoded 32-byte key

    def test_derive_key_different_secrets(self):
        """Different secrets should produce different keys."""
        key1 = _derive_key("secret1")
        key2 = _derive_key("secret2")

        assert key1 != key2

    def test_derive_key_empty_secret(self):
        """Empty secret should still produce a valid key."""
        key = _derive_key("")

        assert key is not None
        assert len(key) == 44

    def test_derive_key_unicode(self):
        """Unicode secrets should be handled correctly."""
        key = _derive_key("contraseña-🔐")

        assert key is not None
        assert len(key) == 44


class TestEncryptSecret:
    """Test symmetric encryption functionality."""

    def test_encrypt_basic_string(self):
        """Basic encryption should produce a token."""
        secret = "encryption-key"
        value = "sensitive-data"

        token = encrypt_secret(secret, value)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        assert token != value  # Encrypted should differ from plain

    def test_encrypt_empty_string(self):
        """Empty strings should be encrypted."""
        token = encrypt_secret("key", "")

        assert token is not None
        assert len(token) > 0

    def test_encrypt_long_string(self):
        """Long strings should be encrypted."""
        secret = "key"
        value = "x" * 10000

        token = encrypt_secret(secret, value)

        assert token is not None
        assert len(token) > 0

    def test_encrypt_special_characters(self):
        """Special characters should be handled."""
        secret = "key"
        value = "!@#$%^&*()[]{}|\\:;\"'<>,.?/"

        token = encrypt_secret(secret, value)

        assert token is not None
        assert len(token) > 0

    def test_encrypt_unicode(self):
        """Unicode characters should be encrypted."""
        secret = "key"
        value = "日本語 🔐 Français"

        token = encrypt_secret(secret, value)

        assert token is not None
        assert len(token) > 0

    def test_encrypt_produces_url_safe_base64(self):
        """Encrypted token should be URL-safe base64."""
        token = encrypt_secret("key", "value")

        # URL-safe base64 uses only: A-Z, a-z, 0-9, -, _
        import re
        assert re.match(r'^[A-Za-z0-9_-]+={0,2}$', token)

    def test_encrypt_different_tokens_for_same_value(self):
        """Encryption should include randomness (different tokens for same value)."""
        secret = "key"
        value = "data"

        token1 = encrypt_secret(secret, value)
        token2 = encrypt_secret(secret, value)

        # Fernet includes timestamp, so tokens should differ
        assert token1 != token2


class TestDecryptSecret:
    """Test symmetric decryption functionality."""

    def test_decrypt_valid_token(self):
        """Valid encrypted token should decrypt to original value."""
        secret = "my-key"
        original = "sensitive-data"

        token = encrypt_secret(secret, original)
        decrypted = decrypt_secret(secret, token)

        assert decrypted == original

    def test_decrypt_wrong_secret(self):
        """Decryption with wrong secret should return None."""
        token = encrypt_secret("correct-key", "data")
        decrypted = decrypt_secret("wrong-key", token)

        assert decrypted is None

    def test_decrypt_invalid_token_format(self):
        """Invalid token format should return None."""
        decrypted = decrypt_secret("key", "invalid-token")

        assert decrypted is None

    def test_decrypt_empty_token(self):
        """Empty token should return None."""
        decrypted = decrypt_secret("key", "")

        assert decrypted is None

    def test_decrypt_malformed_base64(self):
        """Malformed base64 should return None."""
        decrypted = decrypt_secret("key", "not-base64-!!!###")

        assert decrypted is None

    def test_decrypt_empty_string_value(self):
        """Encrypted empty string should decrypt correctly."""
        secret = "key"
        token = encrypt_secret(secret, "")
        decrypted = decrypt_secret(secret, token)

        assert decrypted == ""

    def test_decrypt_unicode(self):
        """Unicode values should decrypt correctly."""
        secret = "key"
        original = "日本語 🔐 Français"

        token = encrypt_secret(secret, original)
        decrypted = decrypt_secret(secret, token)

        assert decrypted == original

    def test_decrypt_long_string(self):
        """Long encrypted strings should decrypt correctly."""
        secret = "key"
        original = "x" * 10000

        token = encrypt_secret(secret, original)
        decrypted = decrypt_secret(secret, token)

        assert decrypted == original

    def test_decrypt_special_characters(self):
        """Special characters should decrypt correctly."""
        secret = "key"
        original = "!@#$%^&*()[]{}|\\:;\"'<>,.?/"

        token = encrypt_secret(secret, original)
        decrypted = decrypt_secret(secret, token)

        assert decrypted == original


class TestEncryptDecryptRoundTrip:
    """Test complete encrypt-decrypt cycles."""

    @pytest.mark.parametrize("value", [
        "simple-string",
        "",
        "x" * 1000,
        "🔐 Unicode 日本語",
        "Line\nBreaks\r\nIncluded",
        '{"json": "value", "nested": {"key": "data"}}',
        "Special: !@#$%^&*()",
    ])
    def test_roundtrip_various_values(self, value):
        """Various values should survive encrypt-decrypt roundtrip."""
        secret = "test-key"

        token = encrypt_secret(secret, value)
        decrypted = decrypt_secret(secret, token)

        assert decrypted == value

    def test_roundtrip_with_different_secrets_fails(self):
        """Roundtrip with different secrets should fail gracefully."""
        original = "data"

        token = encrypt_secret("key1", original)
        decrypted = decrypt_secret("key2", token)

        assert decrypted is None  # Should not decrypt

    def test_multiple_roundtrips_same_secret(self):
        """Multiple encryptions with same secret should all decrypt correctly."""
        secret = "consistent-key"
        values = ["value1", "value2", "value3"]

        tokens = [encrypt_secret(secret, v) for v in values]
        decrypted = [decrypt_secret(secret, t) for t in tokens]

        assert decrypted == values


class TestSecurityProperties:
    """Test security-critical properties."""

    def test_cipher_uses_same_key_for_same_secret(self):
        """Same secret should produce same cipher (for consistency)."""
        cipher1 = _get_cipher("my-secret")
        cipher2 = _get_cipher("my-secret")

        # Both should encrypt to tokens that can decrypt with either
        value = "test-data"
        token = cipher1.encrypt(value.encode()).decode()
        decrypted = cipher2.decrypt(token.encode()).decode()

        assert decrypted == value

    def test_different_secrets_produce_different_ciphers(self):
        """Different secrets should produce incompatible ciphers."""
        cipher1 = _get_cipher("secret1")
        cipher2 = _get_cipher("secret2")

        value = "test-data"
        token = cipher1.encrypt(value.encode()).decode()

        # Attempting to decrypt with wrong cipher should raise
        from cryptography.fernet import InvalidToken
        with pytest.raises(InvalidToken):
            cipher2.decrypt(token.encode())

    def test_encrypted_tokens_contain_no_plaintext(self):
        """Encrypted tokens should not contain original plaintext."""
        secret = "key"
        sensitive = "credit-card-1234-5678"

        token = encrypt_secret(secret, sensitive)

        # Token should not contain any part of the original
        assert "1234" not in token
        assert "5678" not in token
        assert "credit" not in token.lower()

    def test_key_derivation_produces_valid_fernet_key(self):
        """Derived key should be valid for Fernet encryption."""
        from cryptography.fernet import Fernet

        key = _derive_key("any-secret")

        # Should not raise when creating Fernet instance
        cipher = Fernet(key)

        # Should work for encryption
        token = cipher.encrypt(b"test")
        assert cipher.decrypt(token) == b"test"


class TestErrorHandling:
    """Test error cases and edge conditions."""

    def test_decrypt_with_none_returns_none(self):
        """Decrypt should handle None gracefully."""
        # This tests defensive programming
        try:
            result = decrypt_secret("key", None)
            # If it doesn't raise, result should be None
            assert result is None
        except (AttributeError, TypeError):
            # Also acceptable - function may not handle None
            pass

    def test_encrypt_with_non_string_secret(self):
        """Non-string secrets should be handled or raise."""
        # Test that the function has proper type handling
        with pytest.raises((TypeError, AttributeError)):
            encrypt_secret(123, "value")

    def test_decrypt_corrupted_token(self):
        """Corrupted token (valid base64, invalid Fernet) should return None."""
        secret = "key"
        valid_token = encrypt_secret(secret, "data")

        # Corrupt by modifying a character (still valid base64)
        corrupted = list(valid_token)
        corrupted[10] = 'X' if corrupted[10] != 'X' else 'Y'
        corrupted_token = ''.join(corrupted)

        decrypted = decrypt_secret(secret, corrupted_token)

        assert decrypted is None
