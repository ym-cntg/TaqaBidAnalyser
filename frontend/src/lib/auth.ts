/**
 * Demo-only identity gate. There is no real backend user/session model —
 * this just captures "who's working on this" (used to prefill things like
 * the template-lock name) and gates access to the app past /login. It is
 * not a security boundary: the API trusts every request regardless of what
 * this stores. See PROGRESS.md for why a real auth system was explicitly
 * out of scope for this pass.
 */

const STORAGE_KEY = "taqa_bid_analyzer_identity";

export interface Identity {
  name: string;
  email: string;
}

export function getIdentity(): Identity | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.name === "string") return parsed;
    return null;
  } catch {
    return null;
  }
}

export function setIdentity(identity: Identity): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
}

export function clearIdentity(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}
