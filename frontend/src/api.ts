export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  })
  if (resp.status === 401) {
    throw new UnauthenticatedError()
  }
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`${resp.status} ${resp.statusText}: ${body}`)
  }
  return resp.json() as Promise<T>
}

export class UnauthenticatedError extends Error {
  constructor() {
    super("unauthenticated")
    this.name = "UnauthenticatedError"
  }
}
