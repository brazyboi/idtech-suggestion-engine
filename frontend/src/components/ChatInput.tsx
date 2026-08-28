import { useState, useRef, useEffect } from "react";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Ask about specs, compatibility, verticals…",
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  // Auto-focus when the input becomes enabled (e.g., after AI finishes responding)
  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="flex items-end gap-2 px-4 py-4 border-t chat-bg" style={{ borderColor: "var(--border)" }}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none rounded-lg px-3 py-2 text-sm leading-relaxed overflow-hidden bubble-user-bg text-primary border focus:outline-none disabled:opacity-50"
        style={{ borderColor: "var(--button-border)" }}
      />
      <button
        onClick={submit}
        disabled={!canSend}
        className="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-lg btn-accent transition-opacity disabled:opacity-30 active:scale-95"
        aria-label="Send message"
        style={{ boxShadow: '0 1px 0 rgba(0,0,0,0.3)' }}
      >
        <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
          <path
            d="M1.5 7h11M8 2.5L12.5 7 8 11.5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}