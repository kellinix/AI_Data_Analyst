/** Allow redirects only to paths within this application. */
export function safeRedirect(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value) || /%(?:2f|5c)/i.test(value)) {
    return "/dashboard"
  }
  return value
}
