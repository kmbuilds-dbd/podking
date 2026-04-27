import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { ListenButton } from "@/components/ListenButton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listSummaries, listTags, search } from "@/api"
import type { SearchResult, Summary } from "@/api"

function SummaryCard({
  summaryId,
  episodeTitle,
  episodeAuthor,
  tldr,
  tags,
  href,
  score,
}: {
  summaryId: string
  episodeTitle: string
  episodeAuthor?: string | null
  tldr: string
  tags: { name: string }[]
  href: string
  score?: number
}) {
  return (
    <article className="paper-card p-4 h-full flex flex-col gap-2">
      <Link to={href} className="space-y-1.5 flex-1 group">
        <h3
          className="font-serif text-[17px] leading-snug font-semibold tracking-tightest line-clamp-2 group-hover:text-foreground transition-colors"
          title={episodeTitle}
        >
          {episodeTitle}
        </h3>
        {episodeAuthor && (
          <p className="text-xs text-muted-foreground truncate">{episodeAuthor}</p>
        )}
        <p className="text-[13px] leading-relaxed text-muted-foreground line-clamp-3">
          {tldr}
        </p>
      </Link>
      <div className="flex gap-1 flex-wrap items-center pt-1.5 mt-auto">
        {tags.slice(0, 4).map((t) => (
          <span
            key={t.name}
            className="text-[11px] bg-secondary/70 text-secondary-foreground rounded px-1.5 py-0.5"
          >
            {t.name}
          </span>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {score != null && (
            <span className="text-[10px] text-muted-foreground/60 font-mono">
              {score.toFixed(2)}
            </span>
          )}
          <ListenButton summaryId={summaryId} />
        </div>
      </div>
    </article>
  )
}

function summaryToCard(s: Summary) {
  return {
    summaryId: s.id,
    episodeTitle: s.episode.title ?? s.episode.source_url,
    episodeAuthor: s.episode.author,
    tldr: s.content.tldr,
    tags: s.tags,
    href: `/summary/${s.id}`,
  }
}

function searchResultToCard(r: SearchResult) {
  return {
    summaryId: r.summary_id,
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
  const totalCount = !isSearching ? summaries.data?.length : undefined

  const clearSearch = () => {
    setQ("")
    setSubmittedQ("")
    setActiveTag(null)
  }

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-5xl mx-auto px-6 pt-10 pb-16 space-y-8">
        <div className="space-y-2">
          <p className="eyebrow">Library</p>
          <h1 className="font-serif text-4xl sm:text-5xl tracking-tightest font-semibold leading-[1.05]">
            {isSearching ? (
              <>
                Searching{" "}
                <span className="italic text-muted-foreground">
                  {submittedQ ? `"${submittedQ}"` : `#${activeTag}`}
                </span>
              </>
            ) : (
              <>
                Everything you've{" "}
                <span className="italic text-muted-foreground">
                  meant to listen to.
                </span>
              </>
            )}
          </h1>
          {!isSearching && totalCount != null && totalCount > 0 && (
            <p className="text-sm text-muted-foreground">
              {totalCount} {totalCount === 1 ? "summary" : "summaries"} in your
              library.
            </p>
          )}
        </div>

        <div className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              setSubmittedQ(q.trim())
            }}
          >
            <Input
              placeholder="Search by phrase or topic…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="flex-1 h-10"
            />
            <Button type="submit" disabled={!q.trim() && !submittedQ}>
              Search
            </Button>
            {isSearching && (
              <Button type="button" variant="ghost" onClick={clearSearch}>
                Clear
              </Button>
            )}
          </form>

          {tags.data && tags.data.length > 0 && (
            <div className="flex gap-1.5 flex-wrap">
              {tags.data.map((t) => (
                <button
                  key={t.name}
                  onClick={() =>
                    setActiveTag(activeTag === t.name ? null : t.name)
                  }
                  className={`text-xs rounded-full px-2.5 py-1 border transition-colors ${
                    activeTag === t.name
                      ? "bg-foreground text-background border-foreground"
                      : "bg-secondary/60 text-foreground border-transparent hover:bg-secondary"
                  }`}
                >
                  {t.name}
                  <span className="ml-1 text-muted-foreground">
                    {t.count}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {isLoading && (
          <p className="text-sm text-muted-foreground">
            {isSearching ? "Searching…" : "Loading…"}
          </p>
        )}

        {isSearching && searchResults.isError && (
          <p className="text-sm text-destructive">Search failed.</p>
        )}

        {!isLoading && cards.length === 0 && (
          <div className="paper-card p-8 text-center space-y-2">
            <p className="font-serif text-lg">
              {isSearching ? (
                <>No matches {submittedQ && <em>for "{submittedQ}"</em>}.</>
              ) : (
                <>Your library is empty.</>
              )}
            </p>
            {!isSearching && (
              <p className="text-sm text-muted-foreground">
                <Link to="/jobs" className="underline underline-offset-4">
                  Paste a podcast or video URL
                </Link>{" "}
                to add the first summary.
              </p>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cards.map((c, i) => (
            <SummaryCard key={c.href + i} {...c} />
          ))}
        </div>
      </div>
    </div>
  )
}
