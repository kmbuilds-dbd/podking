import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import {
  listSubscriptionEpisodes,
  processSubscriptionEpisode,
} from "@/api"
import type { FeedEpisode } from "@/api"

function formatDuration(seconds: number | null): string {
  if (!seconds) return ""
  const m = Math.floor(seconds / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const mm = m % 60
  return mm ? `${h}h ${mm}m` : `${h}h`
}

function EpisodeRow({
  episode,
  onSummarize,
  isQueueing,
}: {
  episode: FeedEpisode
  onSummarize: () => void
  isQueueing: boolean
}) {
  const dateStr = episode.published_at_ms
    ? new Date(episode.published_at_ms).toLocaleDateString()
    : ""
  const meta = [dateStr, formatDuration(episode.duration_seconds)]
    .filter(Boolean)
    .join(" · ")

  return (
    <div className="flex items-start gap-3 border rounded p-3">
      {episode.thumbnail && (
        <img
          src={episode.thumbnail}
          alt=""
          className="w-12 h-12 rounded object-cover shrink-0"
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium" title={episode.title ?? ""}>
          {episode.title ?? "(untitled episode)"}
        </p>
        {meta && <p className="text-xs text-muted-foreground">{meta}</p>}
        {episode.description && (
          <p
            className="text-xs text-muted-foreground line-clamp-2 mt-0.5"
            // RSS descriptions are usually plain text but may contain HTML
            // entities — render as text to be safe.
          >
            {episode.description.replace(/<[^>]+>/g, "").slice(0, 240)}
          </p>
        )}
      </div>
      {episode.processed ? (
        <span className="text-xs text-green-600 font-medium shrink-0 self-center">
          ✓ Summarized
        </span>
      ) : (
        <Button
          variant="outline"
          size="sm"
          onClick={onSummarize}
          disabled={isQueueing}
          className="shrink-0"
        >
          {isQueueing ? "Queueing…" : "Summarize"}
        </Button>
      )}
    </div>
  )
}

export default function SubscriptionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [pendingExternalId, setPendingExternalId] = useState<string | null>(null)

  const data = useQuery({
    queryKey: ["subscription-episodes", id],
    queryFn: () => listSubscriptionEpisodes(id!),
    enabled: !!id,
  })

  const summarize = useMutation({
    mutationFn: (external_id: string) =>
      processSubscriptionEpisode(id!, external_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] })
      navigate("/jobs")
    },
    onError: () => setPendingExternalId(null),
  })

  if (!id) return null

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <Link
          to="/subscriptions"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← All subscriptions
        </Link>

        {data.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {data.isError && (
          <p className="text-sm text-red-600">
            Failed to load episodes: {String(data.error)}
          </p>
        )}

        {data.data && (
          <>
            <div>
              <h1 className="text-xl font-semibold">
                {data.data.subscription.title ?? data.data.subscription.feed_url}
              </h1>
              <p className="text-xs text-muted-foreground">
                {data.data.subscription.kind === "youtube_channel"
                  ? "YouTube channel"
                  : "Podcast"}
              </p>
            </div>

            <section className="space-y-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Recent episodes
              </h2>
              {data.data.episodes.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No episodes found in this feed.
                </p>
              )}
              <div className="space-y-2">
                {data.data.episodes.map((ep) => (
                  <EpisodeRow
                    key={ep.external_id}
                    episode={ep}
                    onSummarize={() => {
                      setPendingExternalId(ep.external_id)
                      summarize.mutate(ep.external_id)
                    }}
                    isQueueing={
                      pendingExternalId === ep.external_id && summarize.isPending
                    }
                  />
                ))}
              </div>
              {summarize.isError && (
                <p className="text-sm text-red-600">
                  {String(summarize.error)}
                </p>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
