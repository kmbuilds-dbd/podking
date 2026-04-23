import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { search, listTags } from "@/api"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function Search() {
  const [q, setQ] = useState("")
  const [submittedQ, setSubmittedQ] = useState("")
  const [activeTag, setActiveTag] = useState<string | null>(null)

  const tags = useQuery({ queryKey: ["tags"], queryFn: listTags })

  const results = useQuery({
    queryKey: ["search", submittedQ, activeTag],
    queryFn: () => search(submittedQ, activeTag ?? undefined),
    enabled: submittedQ.length > 0,
  })

  return (
    <div className="min-h-screen p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Home</Link>
        <h1 className="text-xl font-semibold">Search</h1>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); setSubmittedQ(q.trim()) }}
      >
        <Input
          placeholder="Search your library…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1"
        />
        <Button type="submit" disabled={!q.trim()}>Search</Button>
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
                  : "bg-secondary text-foreground border-transparent"
              }`}
            >
              {t.name} ({t.count})
            </button>
          ))}
        </div>
      )}

      {results.isLoading && <p className="text-sm text-muted-foreground">Searching…</p>}
      {results.isError && <p className="text-sm text-red-600">Search failed.</p>}

      {results.data?.length === 0 && submittedQ && (
        <p className="text-sm text-muted-foreground">No results for "{submittedQ}".</p>
      )}

      <div className="space-y-3">
        {results.data?.map((r) => (
          <Link key={r.summary_id} to={`/summary/${r.summary_id}`}>
            <div className="border rounded p-3 space-y-1 hover:bg-accent transition-colors cursor-pointer">
              <p className="text-sm font-medium">
                {r.episode.title ?? r.episode.source_url}
              </p>
              <p className="text-xs text-muted-foreground">{r.summary.content.tldr}</p>
              <div className="flex gap-1 flex-wrap">
                {r.summary.tags.slice(0, 4).map((t) => (
                  <span key={t.name} className="text-xs bg-secondary rounded px-1.5 py-0.5">
                    {t.name}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground opacity-50">
                score: {r.score.toFixed(3)}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
