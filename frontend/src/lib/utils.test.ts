import { describe, expect, it } from "vitest";

import { cn, formatPct, formatPnl, formatPrice } from "./utils";

describe("cn", () => {
  it("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-buy", undefined, false, "font-bold")).toBe("text-buy font-bold");
  });
});

describe("formatPrice", () => {
  it("formats to the given precision", () => {
    expect(formatPrice(157.1234, 3)).toBe("157.123");
    expect(formatPrice(1.07345, 5)).toBe("1.07345");
  });
  it("handles null/undefined/NaN", () => {
    expect(formatPrice(null)).toBe("—");
    expect(formatPrice(undefined)).toBe("—");
    expect(formatPrice(NaN)).toBe("—");
  });
});

describe("formatPnl", () => {
  it("prefixes a plus sign for positive values", () => {
    expect(formatPnl(1000)).toBe("+1,000");
  });
  it("does not double up the minus sign for negative values", () => {
    expect(formatPnl(-500)).toBe("-500");
  });
  it("handles zero without a sign", () => {
    expect(formatPnl(0)).toBe("0");
  });
});

describe("formatPct", () => {
  it("formats with a percent-style sign and fixed digits", () => {
    expect(formatPct(2.5)).toBe("+2.50%");
    expect(formatPct(-1.234, 1)).toBe("-1.2%");
  });
});
