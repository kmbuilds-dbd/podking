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
  if (resp.status === 204) {
    return undefined as T
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

// ── types ──────────────────────────────────────────────────────────────────

export interface Job {
  id: string
  kind: string
  source_url: string | null
  episode_id: string | null
  status: string
  progress_pct: number
  progress_message: string | null
  error: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Episode {
  id: string
  source_type: string
  source_url: string
  external_id: string
  title: string | null
  author: string | null
  published_at: string | null
  duration_seconds: number | null
  thumbnail_url: string | null
  created_at: string
}

export interface SummaryTag {
  name: string
  source: "llm" | "user"
}

export interface Summary {
  id: string
  episode: Episode
  system_prompt: string
  model: string
  content: {
    tldr: string
    key_points: string[]
    quotes: { text: string; speaker: string | null }[]
    suggested_tags: string[]
  }
  tags: SummaryTag[]
  created_at: string
}

export interface SearchResult {
  summary_id: string
  score: number
  matched_fields: string[]
  episode: Episode
  summary: Summary
}

export interface Subscription {
  id: string
  kind: string
  feed_url: string
  title: string | null
  last_checked_at: string | null
  active: boolean
  created_at: string
}

export interface TagInfo {
  id: string
  name: string
  count: number
}

// ── jobs ──────────────────────────────────────────────────────────────────

export const createJob = (source_url: string) =>
  api<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ source_url }) })

export const listJobs = () => api<Job[]>("/api/jobs")
export const getJob = (id: string) => api<Job>(`/api/jobs/${id}`)

export const createResumamarize = (episode_id: string) =>
  api<Job>("/api/jobs/resummarize", { method: "POST", body: JSON.stringify({ episode_id }) })

// ── summaries ────────────────────────────────────────────────────────────

export const listSummaries = (params?: { limit?: number; cursor?: string; tag?: string }) => {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set("limit", String(params.limit))
  if (params?.cursor) qs.set("cursor", params.cursor)
  if (params?.tag) qs.set("tag", params.tag)
  return api<Summary[]>(`/api/summaries${qs.size ? "?" + qs : ""}`)
}

export const getSummary = (id: string) => api<Summary>(`/api/summaries/${id}`)

export const deleteSummary = (id: string) =>
  api<void>(`/api/summaries/${id}`, { method: "DELETE" })

export const patchSummaryTags = (id: string, add: string[], remove: string[]) =>
  api<Summary>(`/api/summaries/${id}/tags`, {
    method: "POST",
    body: JSON.stringify({ add, remove }),
  })

export const getTranscript = (episode_id: string) =>
  api<{ id: string; source: string; text: string; segments: unknown; created_at: string }>(
    `/api/episodes/${episode_id}/transcript`
  )

// ── search ────────────────────────────────────────────────────────────────

export const search = (q: string, tag?: string) => {
  const qs = new URLSearchParams({ q })
  if (tag) qs.set("tag", tag)
  return api<SearchResult[]>(`/api/search?${qs}`)
}

// ── tags ──────────────────────────────────────────────────────────────────

export const listTags = () => api<TagInfo[]>("/api/tags")

// ── subscriptions ─────────────────────────────────────────────────────────

export const listSubscriptions = () => api<Subscription[]>("/api/subscriptions")

export const createSubscription = (url: string) =>
  api<Subscription>("/api/subscriptions", { method: "POST", body: JSON.stringify({ url }) })

export const deleteSubscription = (id: string) =>
  api<void>(`/api/subscriptions/${id}`, { method: "DELETE" })

export const patchSubscription = (id: string, active: boolean) =>
  api<Subscription>(`/api/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  })
