/** API origin shared by customer and admin requests. */
export const API_BASE =
  (globalThis as { __VITE_API_BASE_URL__?: string }).__VITE_API_BASE_URL__ ??
  (typeof process !== "undefined" ? process.env.VITE_API_BASE_URL : undefined) ??
  "";

export function withApiBase(path: string): string {
  return `${API_BASE}${path}`;
}
