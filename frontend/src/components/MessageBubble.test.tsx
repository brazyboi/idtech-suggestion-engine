// @ts-nocheck
import { render, screen } from "@testing-library/react";
import MessageBubble from "./MessageBubble";
import type { Message } from "../types/messages";

describe("MessageBubble", () => {
  it("renders quick replies for question/clarification style messages", () => {
    const msg: Message = {
      id: "1",
      role: "bot",
      text: "Choose one",
      quickReplies: ["USB", "Ethernet"],
    };
    render(<MessageBubble msg={msg} onQuickReply={() => undefined} />);
    expect(screen.getByText("USB")).toBeTruthy();
    expect(screen.getByText("Ethernet")).toBeTruthy();
  });

  it("renders recommendation card when product is present", () => {
    const msg: Message = {
      id: "2",
      role: "bot",
      text: "Recommendation",
      product: {
        name: "VP3300",
        sku: "VP-3300",
        description: "Best match.",
      },
    };
    render(<MessageBubble msg={msg} onQuickReply={() => undefined} />);
    expect(screen.getByText("Recommended Hardware")).toBeTruthy();
    expect(screen.getByText("VP3300")).toBeTruthy();
    expect(screen.getByText("SKU: VP-3300")).toBeTruthy();
  });
});
