import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import {
  listPromptStyles,
  listSubscriptionEpisodes,
  patchSubscriptionPromptStyle,
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
    <div className="flex items-start gap-3 paper-card p-3">
      {episode.thumbnail && (
        <img
          src={episode.thumbnail}
          alt=""
          className="w-12 h-12 rounded object-cover shrink-0"
        />
      )}
      <div className="flex-1 min-w-0">
        <p
          className="font-serif font-medium text-base leading-snug"
          title={episode.title ?? ""}
        >
          {episode.title ?? "(untitled episode)"}
        </p>
        {meta && <p className="text-xs text-muted-foreground mt-0.5">{meta}</p>}
        {episode.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
            {episode.description.replace(/<[^>]+>/g, "").slice(0, 240)}
          </p>
        )}
      </div>
      {episode.processed ? (
        <span className="text-xs text-emerald-700 font-medium shrink-0 self-center bg-emerald-100/60 rounded px-2 py-1">
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

  const styles = useQuery({
    queryKey: ["prompt-styles"],
    queryFn: listPromptStyles,
  })

  const saveStyle = useMutation({
    mutationFn: (prompt_style_id: string) =>
      patchSubscriptionPromptStyle(id!, prompt_style_id),
    onSuccess: (subscription) => {
      qc.setQueryData<Awaited<ReturnType<typeof listSubscriptionEpisodes>>>(
        ["subscription-episodes", id],
        (current) => current ? { ...current, subscription } : current,
      )
      qc.invalidateQueries({ queryKey: ["subscription-episodes", id] })
      qc.invalidateQueries({ queryKey: ["subscriptions"] })
    },
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
      <div className="max-w-2xl mx-auto px-6 pt-10 pb-16 space-y-8">
        <Link
          to="/subscriptions"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← All subscriptions
        </Link>

        {data.isLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {data.isError && (
          <p className="text-sm text-destructive">
            Failed to load episodes: {String(data.error)}
          </p>
        )}

        {data.data && (
          <>
            <div className="flex items-start gap-5">
              {data.data.subscription.image_url ? (
                <img
                  src={data.data.subscription.image_url}
                  alt=""
                  className="w-24 h-24 rounded-md object-cover shrink-0 border border-border"
                />
              ) : (
                <div className="w-24 h-24 rounded-md bg-secondary shrink-0 border border-border" />
              )}
              <div className="flex-1 min-w-0 space-y-1.5">
                <p className="eyebrow">
                  {data.data.subscription.kind === "youtube_channel"
                    ? "YouTube channel"
                    : "Podcast"}
                </p>
                <h1 className="font-serif text-3xl tracking-tightest font-semibold leading-[1.1]">
                  {data.data.subscription.title ?? "(untitled feed)"}
                </h1>
                <label className="flex items-center gap-2 text-xs text-muted-foreground pt-2">
                  <span>Analysis style</span>
                  <select
                    className="rounded border border-input bg-background px-2 py-1 text-foreground"
                    value={data.data.subscription.prompt_style_id}
                    disabled={styles.isLoading || saveStyle.isPending}
                    onChange={(e) => saveStyle.mutate(e.target.value)}
                  >
                    {styles.data?.map((style) => (
                      <option key={style.id} value={style.id}>
                        {style.label}
                      </option>
                    ))}
                  </select>
                  {saveStyle.isPending && <span>Saving…</span>}
                </label>
              </div>
            </div>

            <section className="space-y-3">
              <h2 className="eyebrow">Recent episodes</h2>
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
                    isQueueing={saveStyle.isPending || (
                      pendingExternalId === ep.external_id && summarize.isPending
                    )}
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
