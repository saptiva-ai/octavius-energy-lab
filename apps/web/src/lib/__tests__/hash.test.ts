/**
 * Tests for hash utility functions
 */

import { sha256Hex } from "../hash";

describe("hash utilities", () => {
  describe("sha256Hex", () => {
    it("should hash empty buffer correctly", async () => {
      const emptyBuffer = new ArrayBuffer(0);
      const hash = await sha256Hex(emptyBuffer);

      // SHA-256 of empty string
      expect(hash).toBe(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      );
      expect(hash).toHaveLength(64); // SHA-256 produces 64 hex characters
    });

    it("should hash string buffer correctly", async () => {
      const text = "hello world";
      const buffer = new TextEncoder().encode(text).buffer;
      const hash = await sha256Hex(buffer);

      // Known SHA-256 hash of "hello world"
      expect(hash).toBe(
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
      );
      expect(hash).toHaveLength(64);
    });

    it("should produce different hashes for different inputs", async () => {
      const buffer1 = new TextEncoder().encode("test1").buffer;
      const buffer2 = new TextEncoder().encode("test2").buffer;

      const hash1 = await sha256Hex(buffer1);
      const hash2 = await sha256Hex(buffer2);

      expect(hash1).not.toBe(hash2);
      expect(hash1).toHaveLength(64);
      expect(hash2).toHaveLength(64);
    });

    it("should produce consistent hashes for same input", async () => {
      const buffer = new TextEncoder().encode("consistent").buffer;

      const hash1 = await sha256Hex(buffer);
      const hash2 = await sha256Hex(buffer);

      expect(hash1).toBe(hash2);
    });

    it("should handle binary data", async () => {
      const binaryData = new Uint8Array([0, 1, 2, 3, 255, 254, 253]);
      const hash = await sha256Hex(binaryData.buffer);

      expect(hash).toHaveLength(64);
      expect(hash).toMatch(/^[0-9a-f]{64}$/); // Only hex characters
    });

    it("should pad hex values correctly", async () => {
      // This tests the padStart(2, '0') logic for single-digit hex values
      const buffer = new TextEncoder().encode("a").buffer;
      const hash = await sha256Hex(buffer);

      // Should not have single-character hex values (all should be padded to 2)
      expect(hash).toHaveLength(64);
      expect(hash).not.toMatch(/[^0-9a-f]/); // Only valid hex
    });

    it("should handle large buffers", async () => {
      const largeText = "x".repeat(10000);
      const buffer = new TextEncoder().encode(largeText).buffer;
      const hash = await sha256Hex(buffer);

      expect(hash).toHaveLength(64);
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });
  });
});
