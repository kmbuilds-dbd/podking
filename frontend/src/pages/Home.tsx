import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useMe } from "@/hooks/useMe"
import { useJobProgress } from "@/hooks/useJobProgress"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createJob, listJobs, listSummaries } from "@/api"
import type { Job, Summary } from "@/api"

function JobCard({ job }: { job: Job }) {
  useJobProgress(["done", "failed"].includes(job.status) ? null : job.id)

  const color =
    job.status === "done"
      ? "text-green-600"
      : job.status === "failed"
        ? "text-red-600"
        : "text-blue-600"

  return (
    <div className="border rounded p-3 space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-sm font-medium truncate max-w-xs">{job.source_url ?? "re-summarize"}</span>
        <span className={`text-xs font-semibold uppercase ${color}`}>{job.status}</span>
      </div>
      {!["done", "failed"].includes(job.status) && (
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className="bg-blue-500 h-1.5 rounded-full transition-all"
            style={{ width: `${job.progress_pct}%` }}
          />
        </div>
      )}
      {job.progress_message && (
        <p className="text-xs text-muted-foreground">{job.progress_message}</p>
      )}
      {job.error && <p className="text-xs text-red-600">{job.error}</p>}
      {job.status === "done" && job.episode_id && (
        <Link to={`/summary/${job.episode_id}`} className="text-xs text-blue-600 underline">
          View summary →
        </Link>
      )}
    </div>
  )
}

function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <Link to={`/summary/${summary.id}`}>
      <div className="border rounded p-3 space-y-1 hover:bg-accent transition-colors cursor-pointer">
        <p className="text-sm font-medium truncate">
          {summary.episode.title ?? summary.episode.source_url}
        </p>
        <p className="text-xs text-muted-foreground">{summary.content.tldr}</p>
        <div className="flex gap-1 flex-wrap">
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
  const me = useMe()
  const qc = useQueryClient()
  const [url, setUrl] = useState("")

  const jobs = useQuery({ queryKey: ["jobs"], queryFn: listJobs, refetchInterval: 5000 })
  const summaries = useQuery({ queryKey: ["summaries"], queryFn: () => listSummaries({ limit: 12 }) })

  const submit = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      setUrl("")
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const activeJobs = (jobs.data ?? []).filter((j) => !["done", "failed"].includes(j.status))
  const recentJobs = (jobs.data ?? []).filter((j) => ["done", "failed"].includes(j.status)).slice(0, 5)

  return (
    <div className="min-h-screen p-6 max-w-3xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold">podking</h1>
          <nav className="flex gap-3 text-sm">
            <Link to="/search" className="text-muted-foreground hover:text-foreground">Search</Link>
            <Link to="/subscriptions" className="text-muted-foreground hover:text-foreground">Subscriptions</Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{me.data?.email}</span>
          <Button variant="outline" asChild size="sm">
            <Link to="/settings">Settings</Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              await fetch("/auth/logout", { method: "POST", credentials: "include" })
              window.location.href = "/login"
            }}
          >
            Logout
          </Button>
        </div>
      </header>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (url.trim()) submit.mutate(url.trim())
        }}
      >
        <Input
          placeholder="Paste a YouTube or Apple Podcast URL…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={submit.isPending}
          className="flex-1"
        />
        <Button type="submit" disabled={submit.isPending || !url.trim()}>
          {submit.isPending ? "Adding…" : "Process"}
        </Button>
      </form>
      {submit.isError && (
        <p className="text-sm text-red-600">{String(submit.error)}</p>
      )}

      {activeJobs.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            In progress
          </h2>
          {activeJobs.map((j) => <JobCard key={j.id} job={j} />)}
        </section>
      )}

      {recentJobs.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Recent jobs
          </h2>
          {recentJobs.map((j) => <JobCard key={j.id} job={j} />)}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Library
        </h2>
        {summaries.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {summaries.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No summaries yet. Paste a URL above to get started.</p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {summaries.data?.map((s) => <SummaryCard key={s.id} summary={s} />)}
        </div>
      </section>
    </div>
  )
}
