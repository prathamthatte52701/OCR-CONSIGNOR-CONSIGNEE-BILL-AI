// Chat UI flags only (never message text): the panel's open flag and the admin each user picked.
// localStorage can throw on access itself (blocked cookies, private mode), so every call is guarded.
export const CHAT_OPEN_KEY = "main-ocr-chat-open";

const CHAT_ADMIN_PREFIX = "main-ocr-chat-admin.";
export const chatAdminKey = (userId) => `${CHAT_ADMIN_PREFIX}${userId}`;

function resolve(storage) {
  try {
    return storage ?? globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function readStored(key, storage) {
  try {
    const s = resolve(storage);
    return s ? s.getItem(key) : null;
  } catch {
    return null;
  }
}

export function writeStored(key, value, storage) {
  try {
    const s = resolve(storage);
    if (!s) return false;
    s.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export const readFlag = (key, storage) => readStored(key, storage) === "true";
export const writeFlag = (key, on, storage) => writeStored(key, on ? "true" : "false", storage);

// Logout (every path): the next person on this browser starts with no chat panel state and no
// remembered admin choice from the previous user.
export function removeChatKeys(storage) {
  try {
    const s = resolve(storage);
    if (!s) return 0;
    const stale = [];
    for (let i = 0; i < s.length; i += 1) {
      const key = s.key(i);
      if (key === CHAT_OPEN_KEY || key?.startsWith(CHAT_ADMIN_PREFIX)) stale.push(key);
    }
    stale.forEach((key) => s.removeItem(key));
    return stale.length;
  } catch {
    return 0;
  }
}
