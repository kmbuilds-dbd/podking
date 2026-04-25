import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { listSummaries } from "@/api"
import type { Summary } from "@/api"

function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <Link to={`/summary/${summary.id}`}>
      <div className="border rounded p-3 space-y-1 hover:bg-accent transition-colors cursor-pointer h-full">
        <p className="text-sm font-medium truncate">
          {summary.episode.title ?? summary.episode.source_url}
        </p>
        {summary.episode.author && (
          <p className="text-xs text-muted-foreground truncate">
            {summary.episode.author}
          </p>
        )}
        <p className="text-xs text-muted-foreground line-clamp-3">
          {summary.content.tldr}
        </p>
        <div className="flex gap-1 flex-wrap pt-1">
          {summary.tags.slice(0, 4).map((t) => (
            <span key={t.name} className="text-xs bg-secondary rounded px-1.5 py-0.5">
              {t.name}
            </span>
          ))}
        </div>
      </div>
    </Link>
  )
}

export default function Home() {
  const summaries = useQuery({
    queryKey: ["summaries"],
    queryFn: () => listSummaries({ limit: 100 }),
  })

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <h1 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Library
        </h1>
        {summaries.isLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {summaries.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No summaries yet.{" "}
            <Link to="/jobs" className="underline text-foreground">
              Add a podcast or video
            </Link>{" "}
            to get started.
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {summaries.data?.map((s) => <SummaryCard key={s.id} summary={s} />)}
        </div>
      </div>
    </div>
  )
}
