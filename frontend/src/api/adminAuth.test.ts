// @ts-nocheck
import { adminFetch, clearAdminKey, getAdminKey, setAdminKey } from "./adminAuth";

describe("adminAuth", () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.restoreAllMocks();
    (global.fetch as jest.Mock).mockReset();
  });

  it("stores and retrieves the admin key via sessionStorage", () => {
    expect(getAdminKey()).toBeNull();
    setAdminKey("secret-key");
    expect(getAdminKey()).toBe("secret-key");
  });

  it("clears the admin key", () => {
    setAdminKey("secret-key");
    clearAdminKey();
    expect(getAdminKey()).toBeNull();
  });

  it("attaches X-Admin-Api-Key when a key is present", async () => {
    setAdminKey("secret-key");
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, status: 200 } as Response);

    await adminFetch("/api/lead/metrics");

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)["X-Admin-Api-Key"]).toBe("secret-key");
  });

  it("omits X-Admin-Api-Key when no key is present", async () => {
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, status: 200 } as Response);

    await adminFetch("/api/lead/metrics");

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.headers).not.toHaveProperty("X-Admin-Api-Key");
  });

  it("does not throw when sessionStorage.getItem throws (private browsing)", () => {
    jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    expect(getAdminKey()).toBeNull();
  });

  it("does not throw when sessionStorage.setItem throws (private browsing)", () => {
    jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    expect(() => setAdminKey("secret-key")).not.toThrow();
  });

  it("does not throw when sessionStorage.removeItem throws (private browsing)", () => {
    jest.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    expect(() => clearAdminKey()).not.toThrow();
  });
});
