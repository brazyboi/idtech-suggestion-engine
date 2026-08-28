export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface SessionResponse {
  session_id: string;
  message: string;
  stage: string;
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
  /** Extracted info from the LLM tool call, we will merge into collected_info on the frontend. */
  new_info?: Record<string, unknown>;
  /** The updated conversation state after processing this turn */
  next_state?: string;
  ui_actions?: string[];
  debug?: Record<string, unknown>;
}

export interface PDFRequest {
  hardware_name: string;
  software_name?: string;
  highlights?: string[];
  explanation: string;
}

const API_BASE =
  (globalThis as { __VITE_API_BASE_URL__?: string }).__VITE_API_BASE_URL__ ??
  (typeof process !== "undefined" ? process.env.VITE_API_BASE_URL : undefined) ??
  "";

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, init);
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

export async function createSession(): Promise<SessionResponse> {
  const response = await apiFetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return response.json() as Promise<SessionResponse>;
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
