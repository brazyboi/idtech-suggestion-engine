/** Runtime admin-key storage and request headers for the /admin surface. */
const ADMIN_KEY_STORAGE_KEY = "idtech_admin_api_key";

export function getAdminKey(): string | null {
  try {
    return sessionStorage.getItem(ADMIN_KEY_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAdminKey(key: string): void {
  try {
    sessionStorage.setItem(ADMIN_KEY_STORAGE_KEY, key);
  } catch {
    // Best-effort — private browsing / storage disabled just means the
    // key won't survive a refresh.
  }
}

export function clearAdminKey(): void {
  try {
    sessionStorage.removeItem(ADMIN_KEY_STORAGE_KEY);
  } catch {
    // no-op
  }
}

function adminHeaders(extra?: HeadersInit): HeadersInit {
  const key = getAdminKey();
  return {
    ...(extra || {}),
    ...(key ? { "X-Admin-Api-Key": key } : {}),
  };
}

/** fetch() wrapper that attaches the admin API key header to every admin request. */
export async function adminFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: adminHeaders(init.headers),
  });
}
