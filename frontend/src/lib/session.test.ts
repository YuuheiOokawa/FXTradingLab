import { describe, expect, it } from "vitest";

import { createSessionToken, verifySessionToken } from "./session";

describe("session tokens", () => {
  it("round-trips: a token signed with a secret verifies with that same secret", async () => {
    const token = await createSessionToken("test-secret-abc");
    expect(await verifySessionToken(token, "test-secret-abc")).toBe(true);
  });

  it("rejects a token signed with a different secret", async () => {
    const token = await createSessionToken("test-secret-abc");
    expect(await verifySessionToken(token, "a-completely-different-secret")).toBe(false);
  });

  it("rejects undefined, empty, and malformed tokens", async () => {
    expect(await verifySessionToken(undefined, "test-secret-abc")).toBe(false);
    expect(await verifySessionToken("", "test-secret-abc")).toBe(false);
    expect(await verifySessionToken("not-a-real-token", "test-secret-abc")).toBe(false);
    expect(await verifySessionToken("only-one-part", "test-secret-abc")).toBe(false);
  });

  it("rejects a tampered payload even if the signature segment is untouched", async () => {
    const token = await createSessionToken("test-secret-abc");
    const [, sig] = token.split(".");
    const tampered = `not-the-real-payload.${sig}`;
    expect(await verifySessionToken(tampered, "test-secret-abc")).toBe(false);
  });

  it("never puts the secret itself into the token value", async () => {
    const secret = "super-secret-value-should-never-appear";
    const token = await createSessionToken(secret);
    expect(token).not.toContain(secret);
  });
});
