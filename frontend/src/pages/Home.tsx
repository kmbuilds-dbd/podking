import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listSummaries, listTags, search } from "@/api"
import type { SearchResult, Summary } from "@/api"

function SummaryCard({
  episodeTitle,
  episodeAuthor,
  tldr,
  tags,
  href,
  score,
}: {
  episodeTitle: string
  episodeAuthor?: string | null
  tldr: string
  tags: { name: string }[]
  href: string
  score?: number
}) {
  return (
    <Link to={href}>
      <div className="border rounded p-3 space-y-1 hover:bg-accent transition-colors cursor-pointer h-full">
        <p className="text-sm font-medium truncate" title={episodeTitle}>
          {episodeTitle}
        </p>
        {episodeAuthor && (
          <p className="text-xs text-muted-foreground truncate">{episodeAuthor}</p>
        )}
        <p className="text-xs text-muted-foreground line-clamp-3">{tldr}</p>
        <div className="flex gap-1 flex-wrap pt-1 items-center">
          {tags.slice(0, 4).map((t) => (
            <span key={t.name} className="text-xs bg-secondary rounded px-1.5 py-0.5">
              {t.name}
            </span>
          ))}
          {score != null && (
            <span className="text-[10px] text-muted-foreground/60 ml-auto">
              {score.toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}

function summaryToCard(s: Summary) {
  return {
    episodeTitle: s.episode.title ?? s.episode.source_url,
    episodeAuthor: s.episode.author,
    tldr: s.content.tldr,
    tags: s.tags,
    href: `/summary/${s.id}`,
  }
}

function searchResultToCard(r: SearchResult) {
  return {
    episodeTitle: r.episode.title ?? r.episode.source_url,
    episodeAuthor: r.episode.author,
    tldr: r.summary.content.tldr,
    tags: r.summary.tags,
    href: `/summary/${r.summary_id}`,
    score: r.score,
  }
}

export default function Home() {
  const [q, setQ] = useState("")
  const [submittedQ, setSubmittedQ] = useState("")
  const [activeTag, setActiveTag] = useState<string | null>(null)

  const isSearching = submittedQ.length > 0 || activeTag !== null

  const summaries = useQuery({
    queryKey: ["summaries"],
    queryFn: () => listSummaries({ limit: 100 }),
    enabled: !isSearching,
  })

  const searchResults = useQuery({
    queryKey: ["search", submittedQ, activeTag],
    queryFn: () => search(submittedQ, activeTag ?? undefined),
    enabled: isSearching,
  })

  const tags = useQuery({ queryKey: ["tags"], queryFn: listTags })

  const cards = isSearching
    ? (searchResults.data ?? []).map(searchResultToCard)
    : (summaries.data ?? []).map(summaryToCard)

  const isLoading = isSearching ? searchResults.isLoading : summaries.isLoading

  const clearSearch = () => {
    setQ("")
    setSubmittedQ("")
    setActiveTag(null)
  }

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Library
          </h1>
          {isSearching && (
            <button
              onClick={clearSearch}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Clear search
            </button>
          )}
        </div>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmittedQ(q.trim())
          }}
        >
          <Input
            placeholder="Search your library — try a phrase or topic…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" disabled={!q.trim() && !submittedQ}>
            Search
          </Button>
        </form>

        {tags.data && tags.data.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {tags.data.map((t) => (
              <button
                key={t.name}
                onClick={() => setActiveTag(activeTag === t.name ? null : t.name)}
                className={`text-xs rounded px-2 py-1 border transition-colors ${
                  activeTag === t.name
                    ? "bg-foreground text-background border-foreground"
                    : "bg-secondary text-foreground border-transparent hover:bg-secondary/70"
                }`}
              >
                {t.name} ({t.count})
              </button>
            ))}
          </div>
        )}

        {isLoading && (
          <p className="text-sm text-muted-foreground">
            {isSearching ? "Searching…" : "Loading…"}
          </p>
        )}

        {isSearching && searchResults.isError && (
          <p className="text-sm text-red-600">Search failed.</p>
        )}

        {!isLoading && cards.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {isSearching ? (
              <>No matches{submittedQ && ` for "${submittedQ}"`}.</>
            ) : (
              <>
                No summaries yet.{" "}
                <Link to="/jobs" className="underline text-foreground">
                  Add a podcast or video
                </Link>{" "}
                to get started.
              </>
            )}
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {cards.map((c, i) => (
            <SummaryCard key={c.href + i} {...c} />
          ))}
        </div>
      </div>
    </div>
  )
}
