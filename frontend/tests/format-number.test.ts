import { describe, it, expect } from "vitest";
import { fmtInt, fmtFloat, fmtBytes, fmtCell } from "@/lib/format-number";

describe("format-number — locale-pinned to en-US for SSR stability", () => {
  describe("fmtInt", () => {
    it("groups thousands with comma", () => {
      expect(fmtInt(1234567)).toBe("1,234,567");
    });

    it("rounds floats", () => {
      expect(fmtInt(1234.7)).toBe("1,235");
    });

    it("returns em-dash for null / undefined / NaN", () => {
      expect(fmtInt(null)).toBe("—");
      expect(fmtInt(undefined)).toBe("—");
      expect(fmtInt(NaN)).toBe("—");
    });

    it("handles zero + negative", () => {
      expect(fmtInt(0)).toBe("0");
      expect(fmtInt(-42)).toBe("-42");
      expect(fmtInt(-1234)).toBe("-1,234");
    });
  });

  describe("fmtFloat", () => {
    it("two decimal places, grouped", () => {
      expect(fmtFloat(1234.5)).toBe("1,234.50");
    });

    it("rounds to 2dp", () => {
      expect(fmtFloat(0.12345)).toBe("0.12");
    });

    it("missing → em-dash", () => {
      expect(fmtFloat(null)).toBe("—");
      expect(fmtFloat(NaN)).toBe("—");
    });
  });

  describe("fmtBytes", () => {
    it("scales by 1024", () => {
      expect(fmtBytes(500)).toBe("500 B");
      expect(fmtBytes(2048)).toBe("2.0 KB");
      expect(fmtBytes(5 * 1024 * 1024)).toBe("5.0 MB");
      expect(fmtBytes(2 * 1024 ** 3)).toBe("2.00 GB");
    });

    it("missing → em-dash", () => {
      expect(fmtBytes(null)).toBe("—");
    });
  });

  describe("fmtCell", () => {
    it("formats integers vs floats", () => {
      expect(fmtCell(42)).toBe("42");
      expect(fmtCell(3.14)).toBe("3.14");
    });

    it("missing → empty string (cell-friendly, not em-dash)", () => {
      // fmtCell is used by code paths that want blank empties, not "—".
      // This guards against accidental drift.
      expect(fmtCell(null)).toBe("");
      expect(fmtCell(undefined)).toBe("");
    });

    it("passes infinity through as literal", () => {
      expect(fmtCell(Infinity)).toBe("Infinity");
      expect(fmtCell(-Infinity)).toBe("-Infinity");
    });

    it("stringifies non-numerics", () => {
      expect(fmtCell("hello")).toBe("hello");
      expect(fmtCell(true)).toBe("true");
    });
  });
});
