import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useJobProgress } from "@/hooks/useJobProgress"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  createJob,
  deleteJob,
  listJobs,
  listSummaries,
  setJobArchived,
} from "@/api"
import type { Job } from "@/api"

function jobTitle(job: Job): string {
  return (
    job.episode?.title ||
    job.source_url ||
    (job.kind === "resummarize" ? "Re-summarize" : "Untitled")
  )
}

function JobCard({
  job,
  summaryId,
  selected,
  onToggleSelected,
}: {
  job: Job
  summaryId?: string
  selected: boolean
  onToggleSelected: () => void
}) {
  useJobProgress(["done", "failed"].includes(job.status) ? null : job.id)

  const color =
    job.status === "done"
      ? "text-green-600"
      : job.status === "failed"
        ? "text-red-600"
        : "text-blue-600"

  return (
    <div
      className={`border rounded p-3 space-y-1 transition-colors ${
        selected ? "border-blue-500 bg-blue-50/50" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-1"
          checked={selected}
          onChange={onToggleSelected}
          aria-label={`Select ${jobTitle(job)}`}
        />
        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-start gap-2">
            <span className="text-sm font-medium truncate" title={jobTitle(job)}>
              {jobTitle(job)}
            </span>
            <span className={`text-xs font-semibold uppercase shrink-0 ${color}`}>
              {job.status}
            </span>
          </div>
          {job.episode?.author && (
            <p className="text-xs text-muted-foreground truncate">
              {job.episode.author}
            </p>
          )}
          {!["done", "failed"].includes(job.status) && (
            <div className="mt-1 w-full bg-gray-200 rounded-full h-1.5">
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
          {job.status === "done" && summaryId && (
            <Link
              to={`/summary/${summaryId}`}
              className="text-xs text-blue-600 underline"
            >
              View summary →
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

export default function Jobs() {
  const qc = useQueryClient()
  const [url, setUrl] = useState("")
  const [showArchived, setShowArchived] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const jobs = useQuery({
    queryKey: ["jobs", { archived: showArchived }],
    queryFn: () => listJobs({ archived: showArchived }),
    refetchInterval: 5000,
  })
  const summaries = useQuery({
    queryKey: ["summaries"],
    queryFn: () => listSummaries({ limit: 100 }),
  })

  const submit = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      setUrl("")
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const bulkArchive = useMutation({
    mutationFn: async (archived: boolean) => {
      await Promise.all(
        Array.from(selected).map((id) => setJobArchived(id, archived)),
      )
    },
    onSuccess: () => {
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const bulkDelete = useMutation({
    mutationFn: async () => {
      await Promise.all(Array.from(selected).map((id) => deleteJob(id)))
    },
    onSuccess: () => {
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ["jobs"] })
      qc.invalidateQueries({ queryKey: ["summaries"] })
    },
  })

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allJobs = jobs.data ?? []
  const activeJobs = allJobs.filter((j) => !["done", "failed"].includes(j.status))
  const recentJobs = allJobs
    .filter((j) => ["done", "failed"].includes(j.status))
    .slice(0, 50)
  const summaryByEpisode = new Map(
    (summaries.data ?? []).map((s) => [s.episode.id, s.id]),
  )

  const bulkBusy = bulkArchive.isPending || bulkDelete.isPending

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-3xl mx-auto p-6 space-y-6">
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

        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {showArchived ? "Archived" : "Active"}
          </h2>
          <button
            onClick={() => {
              setSelected(new Set())
              setShowArchived((v) => !v)
            }}
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            {showArchived ? "Show active" : "Show archived"}
          </button>
        </div>

        {selected.size > 0 && (
          <div className="sticky top-0 z-10 bg-background border rounded p-2 flex items-center gap-2 shadow-sm">
            <span className="text-sm">{selected.size} selected</span>
            <div className="flex-1" />
            {showArchived ? (
              <Button
                variant="outline"
                size="sm"
                disabled={bulkBusy}
                onClick={() => bulkArchive.mutate(false)}
              >
                Unarchive
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                disabled={bulkBusy}
                onClick={() => bulkArchive.mutate(true)}
              >
                Archive
              </Button>
            )}
            <Button
              variant="destructive"
              size="sm"
              disabled={bulkBusy}
              onClick={() => {
                if (confirm(`Delete ${selected.size} job(s) and their summaries?`)) {
                  bulkDelete.mutate()
                }
              }}
            >
              Delete
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={bulkBusy}
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
          </div>
        )}

        {activeJobs.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              In progress
            </h3>
            {activeJobs.map((j) => (
              <JobCard
                key={j.id}
                job={j}
                summaryId={j.episode_id ? summaryByEpisode.get(j.episode_id) : undefined}
                selected={selected.has(j.id)}
                onToggleSelected={() => toggleSelected(j.id)}
              />
            ))}
          </section>
        )}

        {recentJobs.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {showArchived ? "Archived" : "Recent"}
            </h3>
            {recentJobs.map((j) => (
              <JobCard
                key={j.id}
                job={j}
                summaryId={j.episode_id ? summaryByEpisode.get(j.episode_id) : undefined}
                selected={selected.has(j.id)}
                onToggleSelected={() => toggleSelected(j.id)}
              />
            ))}
          </section>
        )}

        {activeJobs.length === 0 && recentJobs.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {showArchived
              ? "No archived jobs."
              : "No active jobs. Paste a URL above to get started."}
          </p>
        )}
      </div>
    </div>
  )
}
