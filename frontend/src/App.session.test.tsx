// @ts-nocheck
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

const SESSION_ID_KEY = "idtech_chat_session_id";
const SESSION_TOKEN_KEY = "idtech_chat_session_token";

describe("App session init", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
  });

  it("resumes with the stored id and token when both are present", async () => {
    localStorage.setItem(SESSION_ID_KEY, "session-1");
    localStorage.setItem(SESSION_TOKEN_KEY, "token-1");
    const resumeSpy = jest.spyOn(client, "resumeSession").mockResolvedValue({
      session_id: "session-1",
      exists: true,
      history: [{ role: "bot", content: "welcome back" }],
      stage: "collecting_info",
    });

    render(<App />);

    await waitFor(() => expect(resumeSpy).toHaveBeenCalledWith("session-1", "token-1"));
    await waitFor(() => expect(screen.getByText("welcome back")).toBeTruthy());
  });

  it("falls back to a fresh session when the token is missing", async () => {
    localStorage.setItem(SESSION_ID_KEY, "session-1");
    const resumeSpy = jest.spyOn(client, "resumeSession");
    const createSpy = jest.spyOn(client, "createSession").mockResolvedValue({
      session_id: "session-new",
      session_token: "token-new",
      message: "Hi there",
      stage: "start",
    });

    render(<App />);

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    expect(resumeSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("Hi there")).toBeTruthy());
  });

  it("falls back to a fresh session on a 403/resume failure", async () => {
    localStorage.setItem(SESSION_ID_KEY, "session-1");
    localStorage.setItem(SESSION_TOKEN_KEY, "token-1");
    jest.spyOn(client, "resumeSession").mockRejectedValue(new Error("Request failed: 403"));
    const createSpy = jest.spyOn(client, "createSession").mockResolvedValue({
      session_id: "session-new",
      session_token: "token-new",
      message: "Hi there",
      stage: "start",
    });

    render(<App />);

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("Hi there")).toBeTruthy());
  });

  it("does not crash when localStorage.getItem throws (private browsing)", async () => {
    jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    const createSpy = jest.spyOn(client, "createSession").mockResolvedValue({
      session_id: "session-new",
      session_token: "token-new",
      message: "Hi there",
      stage: "start",
    });

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("Hi there")).toBeTruthy());
  });

  it("does not crash when localStorage.setItem throws (private browsing)", async () => {
    jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    jest.spyOn(client, "createSession").mockResolvedValue({
      session_id: "session-new",
      session_token: "token-new",
      message: "Hi there",
      stage: "start",
    });

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByText("Hi there")).toBeTruthy());
  });
});
