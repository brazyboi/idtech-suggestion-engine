import { useEffect, useRef, useState } from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { createSession, sendChatMessage, type ChatResponse } from "./api/client";
import ChatWindow from "./components/ChatWindow";
import DebugPanel from "./components/DebugPanel";
import type { Message, Product } from "./types/messages";
import AdminLayout from "./pages/maintenance/AdminLayout";
import Dashboard from "./pages/maintenance/Dashboard";
import HardwareManager from "./pages/maintenance/HardwareManager";
import AddHardware from "./pages/maintenance/AddHardware";
import EditHardware from "./pages/maintenance/EditHardware";
import SoftwareManager from "./pages/maintenance/SoftwareManager";
import AddSoftware from "./pages/maintenance/AddSoftware";
import EditSoftware from "./pages/maintenance/EditSoftware";
import CategoryManager from "./pages/maintenance/CategoryManager";
import AddCategory from "./pages/maintenance/AddCategory";
import EditCategory from "./pages/maintenance/EditCategory";
import UseCaseManager from "./pages/maintenance/UseCaseManager";
import AddUseCase from "./pages/maintenance/AddUseCase";
import EditUseCase from "./pages/maintenance/EditUseCase";
import PromptManager from "./pages/maintenance/PromptManager";
import DocManager from "./pages/maintenance/DocManager";
import LeadsManager from "./pages/maintenance/LeadsManager";

const normalizeBotText = (raw: string): string => {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      let normalized = line.replace(/^\d+\.\s*/, "");
      normalized = normalized.replace(/^"(.*)"$/, "$1");
      return normalized.trim();
    });

  return lines.join("\n\n");
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const [isLightTheme, setIsLightTheme] = useState(true);
  const [collectedInfo, setCollectedInfo] = useState<Record<string, unknown>>({});
  const [nextState, setNextState] = useState<string | undefined>(undefined);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);

  const collectedInfoRef = useRef(collectedInfo);
  collectedInfoRef.current = collectedInfo;

  useEffect(() => {
    document.body.classList.toggle("light-theme", isLightTheme);
  }, [isLightTheme]);

  useEffect(() => {
    const initSession = async () => {
      try {
        const session = await createSession();
        setSessionId(session.session_id);
        setNextState(session.stage);
        setMessages([
          {
            id: `welcome-${Date.now()}`,
            role: "bot",
            text: session.message,
          },
        ]);
      } catch (err) {
        setMessages([
          {
            id: `welcome-error-${Date.now()}`,
            role: "bot",
            text: `Error: ${String(err)}`,
          },
        ]);
      }
    };

    void initSession();
  }, []);

  async function onSend(text: string) {
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);
    setDisabled(true);

    try {
      const resp: ChatResponse = await sendChatMessage({
        message: text,
        session_id: sessionId,
      });

      if (resp.session_id) {
        setSessionId(resp.session_id);
      }

      const cleanedText = normalizeBotText(resp.text);
      const botMsg: Message = {
        id: `b-${Date.now()}`,
        role: "bot",
        text: cleanedText,
        quickReplies: resp.quick_replies || undefined,
      };

      if (resp.type === "question" || resp.type === "clarification") {
        botMsg.type = "multipleChoice";
        botMsg.choices = (botMsg.quickReplies || []).map((label, idx) => ({
          id: `choice-${Date.now()}-${idx}`,
          label,
        }));
      }

      const mergedInfo = { ...collectedInfoRef.current };
      let resolvedNextState = nextState;

      if (resp.new_info) {
        const override = (resp.new_info as Record<string, unknown>)["__state_override"];
        if (typeof override === "string") {
          resolvedNextState = override;
        }

        for (const [key, value] of Object.entries(resp.new_info)) {
          if (key === "__state_override") {
            continue;
          }

          if (value !== null && typeof value === "object" && !Array.isArray(value)) {
            mergedInfo[key] = {
              ...((mergedInfo[key] as Record<string, unknown> | undefined) || {}),
              ...(value as Record<string, unknown>),
            };
          } else if (value !== undefined) {
            mergedInfo[key] = value;
          }
        }
      }

      if (resp.next_state) {
        resolvedNextState = resp.next_state;
      }

      setNextState(resolvedNextState);
      setCollectedInfo(mergedInfo);
      botMsg.collectedInfo = mergedInfo;
      botMsg.nextState = resolvedNextState;

      if (resp.type === "recommendation" && resp.recommendation?.hardware_items?.length) {
        const hw = resp.recommendation.hardware_items[0];
        const product: Product = {
          name: hw.name ?? "Product",
          sku: (hw.technical_specs?.model_name as string) ?? "",
          description: resp.recommendation.explanation ?? hw.role,
          product_url: hw.product_url,
          installation_docs: resp.recommendation.installation_docs?.map((doc) => ({
            title: doc.title,
            url: doc.url,
          })),
        };
        botMsg.product = product;
      }

      if (resp.ui_actions && resp.ui_actions.length > 0) {
        console.log("[ui_actions]", resp.ui_actions);
      }

      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      const errMsg: Message = {
        id: `e-${Date.now()}`,
        role: "bot",
        text: `Error: ${String(err)}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsTyping(false);
      setDisabled(false);
    }
  }

  return (
    <Router>
      <Routes>
        <Route
          path="/"
          element={
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => setIsLightTheme((prev) => !prev)}
                className="fixed left-4 top-4 z-50 rounded-full border px-3 py-1 text-xs text-primary chat-bg"
                style={{ borderColor: "var(--border)" }}
              >
                {isLightTheme ? "Dark Mode" : "Light Mode"}
              </button>
              <ChatWindow messages={messages} onSend={onSend} isTyping={isTyping} disabled={disabled} />
              <DebugPanel
                collectedInfo={collectedInfo}
                nextState={nextState}
                messageCount={messages.length}
              />
            </div>
          }
        />

        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="leads" element={<LeadsManager />} />
          <Route path="hardware" element={<HardwareManager />} />
          <Route path="hardware/add" element={<AddHardware />} />
          <Route path="hardware/edit/:name" element={<EditHardware />} />
          <Route path="software" element={<SoftwareManager />} />
          <Route path="software/add" element={<AddSoftware />} />
          <Route path="software/edit/:name" element={<EditSoftware />} />
          <Route path="categories" element={<CategoryManager />} />
          <Route path="categories/add" element={<AddCategory />} />
          <Route path="categories/edit/:name" element={<EditCategory />} />
          <Route path="use-cases" element={<UseCaseManager />} />
          <Route path="use-cases/add" element={<AddUseCase />} />
          <Route path="use-cases/edit/:name" element={<EditUseCase />} />
          <Route path="prompts" element={<PromptManager />} />
          <Route path="docs" element={<DocManager />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
