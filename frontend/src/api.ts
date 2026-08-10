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

export interface JobEpisodeMini {
  id: string
  title: string | null
  author: string | null
  thumbnail_url: string | null
  source_url: string
}

export interface Job {
  id: string
  kind: string
  source_url: string | null
  episode_id: string | null
  episode: JobEpisodeMini | null
  status: string
  progress_pct: number
  progress_message: string | null
  error: string | null
  archived: boolean
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
  image_url: string | null
  prompt_style_id: string
  prompt_style: PromptStyle
  last_checked_at: string | null
  created_at: string
}

export interface PromptStyle {
  id: string
  label: string
  prompt_text: string
  created_at: string
  updated_at: string
}

export interface TagInfo {
  id: string
  name: string
  count: number
}

// ── jobs ──────────────────────────────────────────────────────────────────

export const createJob = (source_url: string) =>
  api<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ source_url }) })

export const listJobs = (opts?: { archived?: boolean }) =>
  api<Job[]>(`/api/jobs?archived=${opts?.archived ? "true" : "false"}`)

export const deleteJob = (id: string) =>
  api<void>(`/api/jobs/${id}`, { method: "DELETE" })

export const setJobArchived = (id: string, archived: boolean) =>
  api<Job>(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ archived }),
  })
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

export const patchSubscriptionPromptStyle = (id: string, prompt_style_id: string) =>
  api<Subscription>(`/api/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ prompt_style_id }),
  })

// ── prompt styles ────────────────────────────────────────────────────────

export const listPromptStyles = () => api<PromptStyle[]>("/api/prompt-styles")

export const createPromptStyle = (label: string, prompt_text: string) =>
  api<PromptStyle>("/api/prompt-styles", {
    method: "POST",
    body: JSON.stringify({ label, prompt_text }),
  })

export const patchPromptStyle = (
  id: string,
  body: { label?: string; prompt_text?: string },
) =>
  api<PromptStyle>(`/api/prompt-styles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })

export const deletePromptStyle = (id: string) =>
  api<void>(`/api/prompt-styles/${id}`, { method: "DELETE" })

export interface PodcastSearchResult {
  id: string
  title: string
  publisher: string | null
  description: string | null
  image: string | null
  itunes_id: number
  total_episodes: number | null
  listennotes_url: string | null
}

export const searchPodcasts = (q: string) =>
  api<PodcastSearchResult[]>(`/api/podcast-search?q=${encodeURIComponent(q)}`)

// ── reader links ─────────────────────────────────────────────────────────

export interface FeedUrlResponse {
  token: string
  base_url: string
}

export const getFeedUrl = () => api<FeedUrlResponse>("/api/me/feed-url")

export const regenerateFeedUrl = () =>
  api<FeedUrlResponse>("/api/me/feed-url/regenerate", { method: "POST" })

export function readerUrlFor(baseUrl: string, summaryId: string): string {
  return `${baseUrl}/${summaryId}.html`
}

export interface FeedEpisode {
  external_id: string
  title: string | null
  author: string | null
  published_at_ms: number | null
  duration_seconds: number | null
  thumbnail: string | null
  source_url: string | null
  audio_url: string | null
  description: string | null
  processed: boolean
}

export interface SubscriptionEpisodesResponse {
  subscription: Subscription
  episodes: FeedEpisode[]
}

export const listSubscriptionEpisodes = (id: string) =>
  api<SubscriptionEpisodesResponse>(`/api/subscriptions/${id}/episodes`)

export const processSubscriptionEpisode = (id: string, external_id: string) =>
  api<Job>(`/api/subscriptions/${id}/episodes/process`, {
    method: "POST",
    body: JSON.stringify({ external_id }),
  })

// ── audio episodes ───────────────────────────────────────────────────────

export interface AudioEpisode {
  id: string
  summary_id: string
  job_id: string | null
  title: string
  description: string
  duration_sec: number
  size_bytes: number
  published_url: string | null
  created_at: string
}

export interface AudioJobCreated {
  job_id: string
  audio_episode_id: string | null
}

export const generateSummaryAudio = (
  summaryId: string,
  regenerate = false,
) =>
  api<AudioJobCreated>(
    `/api/summaries/${summaryId}/audio${regenerate ? "?regenerate=true" : ""}`,
    { method: "POST" },
  )

export const listAudioEpisodes = () =>
  api<AudioEpisode[]>(`/api/audio_episodes`)

export const getAudioEpisode = (id: string) =>
  api<AudioEpisode>(`/api/audio_episodes/${id}`)
