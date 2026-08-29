import { useEffect, useRef } from "react";
import ChatInput from "./ChatInput";
import type { Message } from "../types/messages";
import MessageBubble from "./MessageBubble";
import MultipleChoiceMessage from "./MultipleChoiceMessage";
import { CONTACT_URL } from "../constants";

interface ChatWindowProps {
  messages: Message[];
  onSend: (text: string) => void;
  isTyping?: boolean;
  disabled?: boolean;
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2">
      <div className="rounded-2xl rounded-bl-sm px-4 py-3 bot-bubble">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="block h-1.5 w-1.5 rounded-full animate-bounce bot-dot"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow({
  messages,
  onSend,
  isTyping = false,
  disabled = false,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div
      className="mt-4 md:mt-8 mr-0 md:mr-4 ml-auto w-full md:w-[50vh] md:min-w-[400px] max-w-full md:max-w-[50vh] px-4 md:px-6 py-6 md:py-8 flex flex-col h-[100dvh] md:h-[90vh] border-0 md:border-2 md:rounded-l overflow-hidden chat-bg text-primary"
      style={{ borderColor: "var(--border)" }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-b-2 shrink-0" style={{ borderColor: "var(--border)" }}>
        <div>
          <h1 className="brand-name text-2xl font-semibold text-primary">ID TECH Agent</h1>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-4">
        {messages.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-center text-xl text-secondary">
              <i>Ask anything about IDTECH payment hardware.</i>
            </p>
          </div>
        ) : (
          messages.map((msg) =>
            msg.type === "multipleChoice" || (msg.choices && msg.choices.length > 0) ? (
              <MultipleChoiceMessage key={msg.id} msg={msg} onChoice={onSend} />
            ) : (
              <MessageBubble key={msg.id} msg={msg} onQuickReply={onSend} />
            )
          )
        )}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Escalation strip */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 border-t" style={{ borderColor: "var(--border)" }}>
        <span className="text-xs text-secondary">Can't find what you need?</span>
        <a href="mailto:sales@idtechproducts.com" className="text-xs" style={{ color: "var(--accent)" }}>
          Email our team →
        </a>
        <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer" className="text-xs" style={{ color: "var(--accent)" }}>
          Contact sales →
        </a>
      </div>

      {/* Input */}
      <ChatInput onSend={onSend} disabled={disabled} />
    </div>
  );
}
