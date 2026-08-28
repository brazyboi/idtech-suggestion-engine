import type { Message, Product } from "../types/messages";
import { sendChatMessage, ChatResponse } from "../api/client";

interface Props {
  sessionId?: string;
  setMessages: (updater: (prev: Message[]) => Message[]) => void;
  setIsTyping: (v: boolean) => void;
  setDisabled: (v: boolean) => void;
  disabled: boolean;
}

const forceRecommendationPrompt =
  "Recommendation request: Please produce a RecommendationBundle JSON for the following scenario. Business: retail convenience store. Power: plugged into wall outlet. Card types: contact, contactless, magstripe. PIN entry: yes. Device: stand-alone unit. Host: none. Communication: Ethernet. Environment: indoor. Operating temps: 0-40C. Display: yes. Previous products: Ingenico and IDTECH. Return only valid JSON matching the RecommendationBundle schema with fields hardware_items, hardware_name, and explanation. Do not include extra text.";

export default function ForceRecommendationButton({ sessionId, setMessages, setIsTyping, setDisabled, disabled }: Props) {
  const handleClick = async () => {
    const text = forceRecommendationPrompt;
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);
    setDisabled(true);
    try {
      const resp = await sendChatMessage({ message: text, session_id: sessionId });

      const typedResp = resp as ChatResponse;
      const botText = typedResp.text;

      const botMsg: Message = { id: `b-${Date.now()}`, role: "bot", text: botText };

      if (typedResp.type === "recommendation" && typedResp.recommendation?.hardware_items?.length) {
        const hw: any = typedResp.recommendation.hardware_items[0];
        const product: Product = {
          name: hw.name ?? hw.model_name ?? hw.hardware_name ?? typedResp.recommendation.hardware_name ?? "Product",
          sku: hw.sku ?? hw.model?.sku ?? "",
          description: typedResp.recommendation.explanation ?? hw.role ?? JSON.stringify(hw),
        };
        botMsg.product = product;
      }
      setMessages((prev) => [...prev, botMsg]);

    } catch (err) {
      const errMsg: Message = { id: `e-${Date.now()}`, role: "bot", text: `Error: ${String(err)}` };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsTyping(false);
      setDisabled(false);
    }
  };

  return (
    <button
      className="ml-3 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded cursor-pointer"
      onClick={handleClick}
      disabled={disabled}
    >
      Force Recommendation
    </button>
  );
}
