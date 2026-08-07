import { identifyUser, type UserSummary } from "@/lib/api";

// Not real auth -- see backend/api/users.py. Caches whichever identity the
// backend resolved (a forwarded platform header if one exists, else a
// self-reported name) so the user isn't asked again on every visit.
const STORAGE_KEY = "bid-analyzer.identity";

export interface CachedIdentity {
  userId: string;
  displayName: string;
}

export function getCachedIdentity(): CachedIdentity | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CachedIdentity;
  } catch {
    return null;
  }
}

function setCachedIdentity(identity: CachedIdentity): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
}

export function clearCachedIdentity(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

/**
 * Resolves the current user: the backend tries a platform-forwarded
 * identity header first, falling back to whatever display name is passed
 * in (or was previously cached). Throws ApiError with status 400 if
 * neither a platform identity nor a display name is available yet --
 * callers should catch that to show a one-time "what's your name?" prompt,
 * then call this again with one.
 */
export async function resolveIdentity(displayName?: string): Promise<CachedIdentity> {
  const cached = getCachedIdentity();
  const user: UserSummary = await identifyUser(displayName ?? cached?.displayName);
  const identity: CachedIdentity = { userId: user.user_id, displayName: user.display_name };
  setCachedIdentity(identity);
  return identity;
}
