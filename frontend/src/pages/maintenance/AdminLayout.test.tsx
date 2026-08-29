// @ts-nocheck
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AdminLayout from "./AdminLayout";
import { getAdminKey } from "../../api/adminAuth";

// AdminLayout renders an <Outlet/> once authed; a trivial page avoids
// pulling in the full admin route tree for these login-gate tests.
function renderAdminLayout() {
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<div>Dashboard Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("AdminLayout login gate", () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.restoreAllMocks();
    (global.fetch as jest.Mock).mockReset();
  });

  it("shows the admin UI once a stored key is re-verified against the backend", async () => {
    sessionStorage.setItem("idtech_admin_api_key", "existing-key");
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, status: 200 } as Response);

    renderAdminLayout();
    expect(screen.getByText("Checking admin session...")).toBeTruthy();

    await waitFor(() => expect(screen.getByText("Dashboard Content")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith("/api/lead/metrics", expect.anything());
  });

  it("authenticates with a valid key", async () => {
    jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, status: 200 } as Response);

    renderAdminLayout();
    fireEvent.change(screen.getByPlaceholderText("Admin API key"), { target: { value: "good-key" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(screen.getByText("Dashboard Content")).toBeTruthy());
    expect(getAdminKey()).toBe("good-key");
  });

  it("shows an error and clears the key on an invalid key", async () => {
    jest.spyOn(global, "fetch").mockResolvedValue({ ok: false, status: 401 } as Response);

    renderAdminLayout();
    fireEvent.change(screen.getByPlaceholderText("Admin API key"), { target: { value: "bad-key" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(screen.getByText("Invalid admin key")).toBeTruthy());
    expect(getAdminKey()).toBeNull();
  });

  it("returns to the login form, not a broken admin page, when a stale invalid key is stored", async () => {
    sessionStorage.setItem("idtech_admin_api_key", "stale-key");
    jest.spyOn(global, "fetch").mockResolvedValue({ ok: false, status: 401 } as Response);

    renderAdminLayout();
    expect(screen.getByText("Checking admin session...")).toBeTruthy();

    await waitFor(() => expect(screen.getByPlaceholderText("Admin API key")).toBeTruthy());
    expect(getAdminKey()).toBeNull();
  });

  it("returns to the login form when re-verifying a stored key fails outright (network error)", async () => {
    sessionStorage.setItem("idtech_admin_api_key", "stale-key");
    jest.spyOn(global, "fetch").mockRejectedValue(new Error("network down"));

    renderAdminLayout();

    await waitFor(() => expect(screen.getByPlaceholderText("Admin API key")).toBeTruthy());
    expect(getAdminKey()).toBeNull();
  });
});
