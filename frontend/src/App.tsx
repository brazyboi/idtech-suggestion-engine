import { useEffect, useRef, useState } from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { createSession, resumeSession, sendChatMessageStream, type ChatResponse } from "./api/client";
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
import LeadsManager from "./pages/maintenance/LeadsManager";

const SESSION_STORAGE_KEY = "idtech_chat_session_id";
const SESSION_TOKEN_STORAGE_KEY = "idtech_chat_session_token";

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

/** Converts a ChatResponse into the bot message fields used by onSend. */
function applyChatResponse(
  resp: ChatResponse,
  collectedInfo: Record<string, unknown>,
  nextState: string | undefined
): { botMsg: Partial<Message>; mergedInfo: Record<string, unknown>; resolvedNextState: string | undefined } {
  const botMsg: Partial<Message> = {
    quickReplies: resp.quick_replies || undefined,
  };

  if (resp.type === "question" || resp.type === "clarification") {
    botMsg.type = "multipleChoice";
    botMsg.choices = (botMsg.quickReplies || []).map((label, idx) => ({
      id: `choice-${Date.now()}-${idx}`,
      label,
    }));
  }

  const mergedInfo = { ...collectedInfo };
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

  if (resp.ui_actions?.includes("offer_booking")) {
    botMsg.offerBooking = true;
  }

  return { botMsg, mergedInfo, resolvedNextState };
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
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
      // Resume the conversation when the browser still has a session.
      const storedSessionId = (() => {
        try {
          return localStorage.getItem(SESSION_STORAGE_KEY);
        } catch {
          return null;
        }
      })();
      const storedSessionToken = (() => {
        try {
          return localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
        } catch {
          return null;
        }
      })();

      if (storedSessionId && storedSessionToken) {
        try {
          const resumed = await resumeSession(storedSessionId, storedSessionToken);
          if (resumed.exists) {
            setSessionId(resumed.session_id);
            setNextState(resumed.stage);
            setMessages(
              resumed.history.map((entry, idx) => ({
                id: `resumed-${idx}-${Date.now()}`,
                role: entry.role === "user" ? "user" : "bot",
                text: entry.content,
              }))
            );
            return;
          }
        } catch {
          // Fall through to starting a fresh session below.
        }
      }

      try {
        const session = await createSession();
        setSessionId(session.session_id);
        setNextState(session.stage);
        try {
          localStorage.setItem(SESSION_STORAGE_KEY, session.session_id);
          localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, session.session_token);
        } catch {
          // Best-effort — private browsing / storage disabled is fine, it
          // just means this tab won't survive a refresh.
        }
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
    setStatusLabel(null);
    setDisabled(true);

    const botMsgId = `b-${Date.now()}`;
    let streamedText = "";
    let hasStreamedMessage = false;
    // Batch token updates to at most one render per animation frame.
    let flushPending = false;
    const flushStreamedText = () => {
      flushPending = false;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === botMsgId);
        if (idx === -1) return prev;
        const next = [...prev];
        next[idx] = { ...next[idx], text: streamedText };
        return next;
      });
    };
    const scheduleFlush = () => {
      if (flushPending) return;
      flushPending = true;
      requestAnimationFrame(flushStreamedText);
    };

    try {
      await sendChatMessageStream({ message: text, session_id: sessionId }, (event) => {
        if (event.type === "progress") {
          setStatusLabel(event.message ?? null);
          return;
        }

        if (event.type === "token") {
          streamedText += event.delta;
          setStatusLabel(null);
          if (!hasStreamedMessage) {
            hasStreamedMessage = true;
            setMessages((prev) => [
              ...prev,
              { id: botMsgId, role: "bot", text: streamedText, streaming: true },
            ]);
          } else {
            scheduleFlush();
          }
          return;
        }

        if (event.type === "error") {
          // Whatever text streamed before the failure stays on screen —
          // better than discarding a mostly-good answer over a late error.
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === botMsgId);
            const errored: Message = {
              id: `e-${Date.now()}`,
              role: "bot",
              text: streamedText ? `${streamedText}\n\n[${event.message}]` : `Error: ${event.message}`,
            };
            if (idx === -1) return [...prev, errored];
            const next = [...prev];
            next[idx] = errored;
            return next;
          });
          return;
        }

        // event.type === "done"
        const resp = event.response;
        if (resp.session_id) {
          setSessionId(resp.session_id);
          try {
            localStorage.setItem(SESSION_STORAGE_KEY, resp.session_id);
          } catch {
            // Best-effort, see initSession above.
          }
        }

        const { botMsg, mergedInfo, resolvedNextState } = applyChatResponse(
          resp,
          collectedInfoRef.current,
          nextState
        );
        setNextState(resolvedNextState);
        setCollectedInfo(mergedInfo);

        const finalText = normalizeBotText(resp.text);
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === botMsgId);
          const finished: Message = { id: botMsgId, role: "bot", text: finalText, ...botMsg, streaming: false };
          if (idx === -1) return [...prev, finished];
          const next = [...prev];
          next[idx] = finished;
          return next;
        });
      });
    } catch (err) {
      // Request itself failed (network error, non-2xx before any bytes
      // streamed) rather than a mid-stream "error" event.
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === botMsgId);
        const errMsg: Message = { id: `e-${Date.now()}`, role: "bot", text: `Error: ${String(err)}` };
        if (idx === -1 || !hasStreamedMessage) return [...prev, errMsg];
        const next = [...prev];
        next[idx] = errMsg;
        return next;
      });
    } finally {
      setIsTyping(false);
      setStatusLabel(null);
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
              <ChatWindow
                messages={messages}
                onSend={onSend}
                isTyping={isTyping}
                statusLabel={statusLabel}
                disabled={disabled}
              />
              {import.meta.env.DEV && (
                <DebugPanel
                  collectedInfo={collectedInfo}
                  nextState={nextState}
                  messageCount={messages.length}
                />
              )}
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
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
