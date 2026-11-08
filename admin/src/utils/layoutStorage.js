// Chat UI flags only (never message text): the panel's open flag and the user thread an admin last
// had open. localStorage can throw on access itself, so every call is guarded.
export const CHAT_OPEN_KEY = "main-ocr-admin-chat-open";
const CHAT_USER_PREFIX = "main-ocr-admin-chat-user.";

// The chat user an admin last had open, remembered per admin id.
export const chatUserKey = (adminId) => `${CHAT_USER_PREFIX}${adminId}`;

export function readStored(key, storage) {
  try {
    return (storage ?? globalThis.localStorage).getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key, value, storage) {
  try {
    (storage ?? globalThis.localStorage).setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function removeStored(key, storage) {
  try {
    (storage ?? globalThis.localStorage).removeItem(key);
  } catch {
    /* nothing to remove */
  }
}

export const readFlag = (key, storage) => readStored(key, storage) === "true";
export const writeFlag = (key, on, storage) => writeStored(key, on ? "true" : "false", storage);

// Logout: no remembered chat user (and no open-panel flag) stays behind for the next admin here.
export function removeChatUserKeys(storage) {
  try {
    const s = storage ?? globalThis.localStorage;
    const stale = [];
    for (let i = 0; i < s.length; i += 1) {
      const key = s.key(i);
      if (key === CHAT_OPEN_KEY || key?.startsWith(CHAT_USER_PREFIX)) stale.push(key);
    }
    stale.forEach((key) => s.removeItem(key));
    return stale.length;
  } catch {
    return 0;
  }
}
