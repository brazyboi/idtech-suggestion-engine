import { withApiBase } from "./apiBase";

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface SessionResponse {
  session_id: string;
  session_token: string;
  message: string;
  stage: string;
}

export interface SessionResumeResponse {
  session_id: string;
  exists: boolean;
  history: Array<{ role: string; content: string }>;
  stage?: string;
}

export interface InstallationDoc {
  title: string;
  url: string;
}

export interface HardwareRecommendation {
  name: string;
  role: string;
  technical_specs?: Record<string, unknown>;
  product_url?: string;
}

export interface SoftwareRecommendation {
  name: string;
  datasheet_url?: string;
}

export interface RecommendationBundle {
  hardware_name: string;
  hardware_items: HardwareRecommendation[];
  software?: SoftwareRecommendation[];
  highlights?: string[];
  explanation: string;
  installation_docs?: InstallationDoc[];
}

export interface ChatResponse {
  type: "question" | "recommendation" | "clarification" | "error";
  text: string;
  quick_replies?: string[];
  session_id?: string;
  recommendation?: RecommendationBundle;
  /** Lead fields extracted by an LLM tool call. */
  new_info?: Record<string, unknown>;
  /** The updated conversation state after processing this turn */
  next_state?: string;
  ui_actions?: string[];
  debug?: Record<string, unknown>;
}

/** One SSE event from POST /api/chat/stream — see backend/routers/chat.py. */
export type ChatStreamEvent =
  | { type: "progress"; stage: string; tool?: string; message?: string }
  | { type: "token"; delta: string }
  | { type: "done"; response: ChatResponse }
  | { type: "error"; message: string };

export interface PDFRequest {
  hardware_name: string;
  software_name?: string;
  highlights?: string[];
  explanation: string;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(withApiBase(path), init);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed: ${response.status}`);
  }
  return response;
}

export async function sendChatMessage(chatRequest: ChatRequest): Promise<ChatResponse> {
  const response = await apiFetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(chatRequest),
  });

  return response.json() as Promise<ChatResponse>;
}

/**
 * Streams a chat turn via SSE and reports each event to onEvent.
 */
export async function sendChatMessageStream(
  chatRequest: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(withApiBase("/api/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(chatRequest),
    signal,
  });

  if (!response.ok || !response.body) {
    const errorText = response.body ? await response.text() : "";
    throw new Error(errorText || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    // Keep incomplete events buffered across network chunks.
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex).trim();
      buffer = buffer.slice(sepIndex + 2);
      if (!rawEvent.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(rawEvent.slice("data: ".length)) as ChatStreamEvent);
      } catch {
        // Malformed event — skip it rather than crash the whole stream.
      }
    }
  }
}

export async function createSession(): Promise<SessionResponse> {
  const response = await apiFetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return response.json() as Promise<SessionResponse>;
}

export async function resumeSession(sessionId: string, sessionToken: string): Promise<SessionResumeResponse> {
  const response = await apiFetch(`/api/session/${encodeURIComponent(sessionId)}`, {
    headers: { "X-Session-Token": sessionToken },
  });
  return response.json() as Promise<SessionResumeResponse>;
}

export async function downloadPDF(payload: PDFRequest): Promise<Blob> {
  const response = await apiFetch("/api/pdf/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return response.blob();
}

export async function downloadRecommendationPDF(bundle: RecommendationBundle): Promise<Blob> {
  const response = await apiFetch("/api/pdf/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bundle),
  });

  return response.blob();
}
