// @ts-nocheck
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

describe("App chat streaming", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
    jest.spyOn(client, "createSession").mockResolvedValue({
      session_id: "session-1",
      session_token: "token-1",
      message: "Hi, welcome!",
      stage: "greeting",
    });
  });

  async function sendMessage(text: string) {
    await waitFor(() => expect(screen.getByPlaceholderText(/ask about/i)).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/ask about/i), { target: { value: text } });
    fireEvent.keyDown(screen.getByPlaceholderText(/ask about/i), { key: "Enter" });
  }

  it("shows a progress label, then streams tokens, then finalizes on done", async () => {
    let emit: (event: any) => void = () => {};
    jest.spyOn(client, "sendChatMessageStream").mockImplementation((_req, onEvent) => {
      emit = onEvent;
      return new Promise(() => {}); // never resolves — we drive events manually
    });

    render(<App />);
    await sendMessage("What do you have for parking?");

    act(() => emit({ type: "progress", stage: "tool_call", tool: "search_products", message: "Searching products..." }));
    await waitFor(() => expect(screen.getByText("Searching products...")).toBeTruthy());

    act(() => emit({ type: "token", delta: "The " }));
    act(() => emit({ type: "token", delta: "VP3300 " }));
    act(() => emit({ type: "token", delta: "is great." }));
    await waitFor(() => expect(screen.getByText(/VP3300/)).toBeTruthy());

    act(() =>
      emit({
        type: "done",
        response: {
          type: "clarification",
          text: "The VP3300 is great.",
          session_id: "session-1",
        },
      })
    );

    await waitFor(() => expect(screen.getByText("The VP3300 is great.")).toBeTruthy());
    // The streaming cursor is gone and the status line is cleared once done.
    expect(screen.queryByText("Searching products...")).toBeNull();
  });

  it("keeps streamed text on screen and appends the error when the stream fails mid-way", async () => {
    let emit: (event: any) => void = () => {};
    jest.spyOn(client, "sendChatMessageStream").mockImplementation((_req, onEvent) => {
      emit = onEvent;
      return new Promise(() => {});
    });

    render(<App />);
    await sendMessage("Tell me about the VP6300");

    act(() => emit({ type: "token", delta: "The VP6300 supports" }));
    await waitFor(() => expect(screen.getByText(/The VP6300 supports/)).toBeTruthy());

    act(() => emit({ type: "error", message: "Something went wrong processing your message. Please try again." }));
    await waitFor(() =>
      expect(screen.getByText(/The VP6300 supports.*Something went wrong/s)).toBeTruthy()
    );
  });

  it("shows an error message when the stream request itself rejects", async () => {
    jest.spyOn(client, "sendChatMessageStream").mockRejectedValue(new Error("network down"));

    render(<App />);
    await sendMessage("hello");

    await waitFor(() => expect(screen.getByText("Error: Error: network down")).toBeTruthy());
  });
});
