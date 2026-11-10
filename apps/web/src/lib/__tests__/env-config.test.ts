/**
 * Tests for env-config utility functions
 */

import {
  getSaptivaConfig,
  isSaptivaConfigured,
  isDemoMode,
  getApiClientConfig,
  getDemoModeMessage,
} from "../env-config";

describe("env-config", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Reset process.env before each test
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe("getSaptivaConfig", () => {
    it("should return default config when no env vars set", () => {
      delete process.env.SAPTIVA_API_KEY;
      delete process.env.NEXT_PUBLIC_SAPTIVA_BASE_URL;

      const config = getSaptivaConfig();

      expect(config).toEqual({
        apiKey: null,
        baseUrl: "https://api.saptiva.com",
        isDemoMode: true,
      });
    });

    it("should read API key from environment", () => {
      process.env.SAPTIVA_API_KEY = "test-api-key-123";

      const config = getSaptivaConfig();

      expect(config.apiKey).toBe("test-api-key-123");
      expect(config.isDemoMode).toBe(false);
    });

    it("should read custom base URL from environment", () => {
      process.env.NEXT_PUBLIC_SAPTIVA_BASE_URL = "https://custom.api.com";

      const config = getSaptivaConfig();

      expect(config.baseUrl).toBe("https://custom.api.com");
    });

    it("should set isDemoMode false when API key is present", () => {
      process.env.SAPTIVA_API_KEY = "valid-key";

      const config = getSaptivaConfig();

      expect(config.isDemoMode).toBe(false);
    });

    it("should set isDemoMode true when API key is missing", () => {
      delete process.env.SAPTIVA_API_KEY;

      const config = getSaptivaConfig();

      expect(config.isDemoMode).toBe(true);
    });
  });

  describe("isSaptivaConfigured", () => {
    it("should return false when no API key set", () => {
      delete process.env.SAPTIVA_API_KEY;

      expect(isSaptivaConfigured()).toBe(false);
    });

    it("should return false when API key is empty string", () => {
      process.env.SAPTIVA_API_KEY = "";

      expect(isSaptivaConfigured()).toBe(false);
    });

    it("should return true when API key is set", () => {
      process.env.SAPTIVA_API_KEY = "valid-key";

      expect(isSaptivaConfigured()).toBe(true);
    });
  });

  describe("isDemoMode", () => {
    it("should return true when no API key", () => {
      delete process.env.SAPTIVA_API_KEY;

      expect(isDemoMode()).toBe(true);
    });

    it("should return false when API key is set", () => {
      process.env.SAPTIVA_API_KEY = "valid-key";

      expect(isDemoMode()).toBe(false);
    });
  });

  describe("getApiClientConfig", () => {
    it("should return config without Authorization header in demo mode", () => {
      delete process.env.SAPTIVA_API_KEY;

      const config = getApiClientConfig();

      expect(config.headers).toEqual({
        "Content-Type": "application/json",
      });
      expect(config.isDemoMode).toBe(true);
    });

    it("should include Authorization header when API key is set", () => {
      process.env.SAPTIVA_API_KEY = "my-secret-key";

      const config = getApiClientConfig();

      expect(config.headers).toEqual({
        Authorization: "Bearer my-secret-key",
        "Content-Type": "application/json",
      });
      expect(config.isDemoMode).toBe(false);
    });

    it("should use custom base URL if provided", () => {
      process.env.NEXT_PUBLIC_SAPTIVA_BASE_URL = "https://staging.api.com";

      const config = getApiClientConfig();

      expect(config.baseUrl).toBe("https://staging.api.com");
    });

    it("should use default base URL if not provided", () => {
      delete process.env.NEXT_PUBLIC_SAPTIVA_BASE_URL;

      const config = getApiClientConfig();

      expect(config.baseUrl).toBe("https://api.saptiva.com");
    });
  });

  describe("getDemoModeMessage", () => {
    it("should return message when in demo mode", () => {
      delete process.env.SAPTIVA_API_KEY;

      const message = getDemoModeMessage();

      expect(message).toBe(
        "Modo demo activo. Configura SAPTIVA_API_KEY en variables de entorno para funcionalidad completa.",
      );
    });

    it("should return null when not in demo mode", () => {
      process.env.SAPTIVA_API_KEY = "valid-key";

      const message = getDemoModeMessage();

      expect(message).toBeNull();
    });
  });
});
