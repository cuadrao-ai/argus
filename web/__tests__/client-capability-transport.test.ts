import { describe, expect, test } from "bun:test";
import {
  ARGUS_CLIENT_CAPABILITIES,
  argusApiRequestHeaders,
} from "../lib/argus-api-transport";

describe("API client capability negotiation", () => {
  test("advertises dossier conversion support from the shared transport", () => {
    const headers = argusApiRequestHeaders(
      {
        "X-Caller-Header": "preserved",
        "X-Argus-Client-Capabilities": "caller-cannot-override",
      },
      { Authorization: "Bearer test-token" },
      null,
    );

    expect(ARGUS_CLIENT_CAPABILITIES).toEqual([
      "dossier_decision_conversion_v1",
    ]);
    expect(headers.get("X-Argus-Client-Capabilities")).toBe(
      "dossier_decision_conversion_v1",
    );
    expect(headers.get("X-Caller-Header")).toBe("preserved");
    expect(headers.get("Authorization")).toBe("Bearer test-token");
  });
});
