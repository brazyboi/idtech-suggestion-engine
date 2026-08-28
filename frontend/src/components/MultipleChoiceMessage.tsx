import MessageBubble from "./MessageBubble";
import GenericButton from "./GenericButton";
import type { Message } from "../types/messages";

export default function MultipleChoiceMessage({
  msg,
  onChoice,
}: {
  msg: Message;
  onChoice: (label: string) => void;
}) {
  // Render the question using MessageBubble but suppress quickReplies
  const questionMsg: Message = { ...msg, quickReplies: undefined };

  return (
    <div className="flex flex-col gap-2">
      <MessageBubble msg={questionMsg} onQuickReply={onChoice} />

      {msg.choices && msg.choices.length > 0 && (
        <div className="flex flex-wrap gap-2 pl-3">
            {msg.choices.map((c) => (
              <GenericButton
                key={c.id}
                onClick={() => onChoice(c.label)}
                className={`choice-btn ${msg.answered ? "opacity-50 cursor-not-allowed" : "btn-accent"}`}
                disabled={!!msg.answered}
              >
                {c.label}
              </GenericButton>
            ))}
        </div>
      )}
    </div>
  );
}
