// Same-app paths only: "/x" yes; "//host", "/\host", "https://..", "javascript:.." no.
export function isSafePath(path) {
  return typeof path === "string" && /^\/(?![/\\])/.test(path) && !/[\\\s]/.test(path);
}

export function safePath(path, fallback = "/dashboard") {
  return isSafePath(path) ? path : fallback;
}
