import type { Message } from "../types/messages";
import ProductCard from "./ProductCard";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MessageBubble({
  msg,
  onQuickReply,
}: {
  msg: Message;
  onQuickReply: (label: string) => void;
}) {
  const isBot = msg.role === "bot";

  return (
    <div className={`flex flex-col gap-2 ${isBot ? "items-start" : "items-end"}`}>
      {isBot ? (
        <>
          {/* Avatar + text content row */}
          <div className="flex items-start gap-3 w-full">
            <div className="w-8 h-8 rounded-full overflow-hidden flex-shrink-0 bg-[var(--accent)] flex items-center justify-center text-white text-xs font-semibold">
              <img
                src="/bot-avatar.png"
                alt="ID TECH Agent"
                className="w-8 h-8 object-cover"
                onError={(e) => {
                  const img = e.target as HTMLImageElement;
                  img.style.display = "none";
                  if (img.parentElement) {
                    img.parentElement.textContent = "ID";
                  }
                }}
              />
            </div>

            <div className="flex-1 min-w-0">
              <div className="w-full text-sm leading-relaxed text-primary prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.text}
                </ReactMarkdown>
              </div>

              {msg.quickReplies && msg.quickReplies.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {msg.quickReplies.map((label) => (
                    <button
                      key={label}
                      onClick={() => onQuickReply(label)}
                      className="rounded-full border px-3 py-1 text-xs transition-colors btn-accent hover:cursor-pointer"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Product card — full width, outside the avatar column */}
          {msg.product && (
            <div className="w-full px-2">
              <ProductCard product={msg.product} />
            </div>
          )}
        </>
      ) : (
        <div className="self-end max-w-[75%] inline-block">
          <p className="inline-block rounded-2xl px-3 py-2 text-sm leading-relaxed bubble-user-bg">
            {msg.text}
          </p>
        </div>
      )}
    </div>
  );
}
