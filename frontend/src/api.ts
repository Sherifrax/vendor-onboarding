export type RecordRow = Record<string, unknown>;

const baseUrl = import.meta.env.VITE_API_BASE ?? "/api";

export async function api<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Admin-Token": token, ...init.headers },
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Request failed");
  return response.json() as Promise<T>;
}

export async function downloadDocument(documentId: number, filename: string, token: string): Promise<void> {
  const response = await fetch(`${baseUrl}/documents/${documentId}/content`, {
    headers: { "X-Admin-Token": token },
  });
  if (!response.ok) throw new Error("Document download failed");
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

export function formatDate(value: unknown): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(String(value))) : "—";
}
