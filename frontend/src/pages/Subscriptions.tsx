import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listSubscriptions,
  createSubscription,
  deleteSubscription,
  patchSubscription,
  searchPodcasts,
} from "@/api"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { PodcastSearchResult, Subscription } from "@/api"

function SubRow({ sub }: { sub: Subscription }) {
  const qc = useQueryClient()

  const toggle = useMutation({
    mutationFn: () => patchSubscription(sub.id, !sub.active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  })

  const del = useMutation({
    mutationFn: () => deleteSubscription(sub.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  })

  return (
    <div className="flex items-center gap-3 border rounded p-3 hover:bg-accent/40 transition-colors">
      <Link to={`/subscriptions/${sub.id}`} className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{sub.title ?? sub.feed_url}</p>
        <p className="text-xs text-muted-foreground">
          {sub.kind === "youtube_channel" ? "YouTube" : "Podcast"} ·{" "}
          {sub.last_checked_at
            ? `checked ${new Date(sub.last_checked_at).toLocaleDateString()}`
            : "never checked"}
        </p>
      </Link>
      <Button
        variant="outline"
        size="sm"
        onClick={() => toggle.mutate()}
        disabled={toggle.isPending}
        className={sub.active ? "" : "opacity-50"}
      >
        {sub.active ? "Active" : "Paused"}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => { if (confirm("Remove subscription?")) del.mutate() }}
        disabled={del.isPending}
        className="text-red-600 hover:text-red-700"
      >
        ×
      </Button>
    </div>
  )
}

function SearchResultRow({
  result,
  onSubscribe,
  isSubscribing,
}: {
  result: PodcastSearchResult
  onSubscribe: () => void
  isSubscribing: boolean
}) {
  return (
    <div className="flex items-start gap-3 border rounded p-3">
      {result.image && (
        <img
          src={result.image}
          alt=""
          className="w-12 h-12 rounded object-cover shrink-0"
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" title={result.title}>
          {result.title}
        </p>
        {result.publisher && (
          <p className="text-xs text-muted-foreground truncate">
            {result.publisher}
            {result.total_episodes != null && ` · ${result.total_episodes} episodes`}
          </p>
        )}
        {result.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
            {result.description}
          </p>
        )}
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={onSubscribe}
        disabled={isSubscribing}
        className="shrink-0"
      >
        {isSubscribing ? "…" : "Subscribe"}
      </Button>
    </div>
  )
}

export default function Subscriptions() {
  const qc = useQueryClient()
  const [url, setUrl] = useState("")
  const [searchQ, setSearchQ] = useState("")
  const [submittedQ, setSubmittedQ] = useState("")
  const [pendingId, setPendingId] = useState<number | null>(null)

  const subs = useQuery({ queryKey: ["subscriptions"], queryFn: listSubscriptions })

  const search = useQuery({
    queryKey: ["podcast-search", submittedQ],
    queryFn: () => searchPodcasts(submittedQ),
    enabled: submittedQ.length > 0,
  })

  const add = useMutation({
    mutationFn: (target: string) => createSubscription(target),
    onSuccess: () => {
      setUrl("")
      setPendingId(null)
      qc.invalidateQueries({ queryKey: ["subscriptions"] })
    },
    onError: () => {
      setPendingId(null)
    },
  })

  const subscribeFromResult = (r: PodcastSearchResult) => {
    setPendingId(r.itunes_id)
    add.mutate(`https://podcasts.apple.com/podcast/id${r.itunes_id}`)
  }

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <h1 className="text-xl font-semibold">Subscriptions</h1>

        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Find a podcast
          </h2>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              setSubmittedQ(searchQ.trim())
            }}
          >
            <Input
              placeholder="Search podcasts (e.g. 'Lenny's Podcast', 'huberman')…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" disabled={!searchQ.trim()}>
              Search
            </Button>
          </form>
          {search.isLoading && (
            <p className="text-sm text-muted-foreground">Searching…</p>
          )}
          {search.isError && (
            <p className="text-sm text-red-600">
              Search failed: {String(search.error)}
            </p>
          )}
          {search.data && search.data.length === 0 && submittedQ && (
            <p className="text-sm text-muted-foreground">
              No podcasts found for "{submittedQ}".
            </p>
          )}
          {search.data && search.data.length > 0 && (
            <div className="space-y-2">
              {search.data.map((r) => (
                <SearchResultRow
                  key={r.id}
                  result={r}
                  onSubscribe={() => subscribeFromResult(r)}
                  isSubscribing={pendingId === r.itunes_id && add.isPending}
                />
              ))}
            </div>
          )}
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Add by URL
          </h2>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (url.trim()) add.mutate(url.trim())
            }}
          >
            <Input
              placeholder="YouTube channel URL, Apple Podcast URL, or RSS feed URL…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={add.isPending}
              className="flex-1"
            />
            <Button type="submit" disabled={add.isPending || !url.trim()}>
              {add.isPending && pendingId === null ? "Adding…" : "Follow"}
            </Button>
          </form>
          {add.isError && <p className="text-sm text-red-600">{String(add.error)}</p>}
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Following
          </h2>
          {subs.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {subs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No subscriptions yet.</p>
          )}
          <div className="space-y-2">
            {subs.data?.map((s) => <SubRow key={s.id} sub={s} />)}
          </div>
        </section>
      </div>
    </div>
  )
}
