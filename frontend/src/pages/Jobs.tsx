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

  const statusStyles: Record<string, string> = {
    done: "text-emerald-700 bg-emerald-100/60",
    failed: "text-destructive bg-destructive/10",
    queued: "text-foreground/60 bg-foreground/5",
    fetching: "text-amber-800 bg-amber-100/60",
    transcribing: "text-amber-800 bg-amber-100/60",
    summarizing: "text-amber-800 bg-amber-100/60",
    embedding: "text-amber-800 bg-amber-100/60",
  }
  const statusClass = statusStyles[job.status] ?? "text-foreground/60 bg-foreground/5"

  return (
    <div
      className={`paper-card p-3.5 transition-colors ${
        selected ? "border-foreground bg-foreground/[0.03]" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-[5px] accent-foreground"
          checked={selected}
          onChange={onToggleSelected}
          aria-label={`Select ${jobTitle(job)}`}
        />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex justify-between items-start gap-2">
            <span
              className="text-sm font-medium truncate font-serif"
              title={jobTitle(job)}
            >
              {jobTitle(job)}
            </span>
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 shrink-0 ${statusClass}`}
            >
              {job.status}
            </span>
          </div>
          {job.episode?.author && (
            <p className="text-xs text-muted-foreground truncate">
              {job.episode.author}
            </p>
          )}
          {!["done", "failed"].includes(job.status) && (
            <div className="mt-1.5 w-full bg-secondary rounded-full h-1 overflow-hidden">
              <div
                className="bg-foreground h-1 rounded-full transition-all"
                style={{ width: `${job.progress_pct}%` }}
              />
            </div>
          )}
          {job.progress_message && (
            <p className="text-xs text-muted-foreground">
              {job.progress_message}
            </p>
          )}
          {job.error && (
            <p className="text-xs text-destructive">{job.error}</p>
          )}
          {job.status === "done" && summaryId && (
            <Link
              to={`/summary/${summaryId}`}
              className="text-xs text-foreground underline underline-offset-2 hover:text-foreground/70"
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
      <div className="max-w-3xl mx-auto px-6 pt-10 pb-16 space-y-8">
        <div className="space-y-2">
          <p className="eyebrow">Jobs</p>
          <h1 className="font-serif text-4xl tracking-tightest font-semibold leading-[1.05]">
            Add something{" "}
            <span className="italic text-muted-foreground">to listen to.</span>
          </h1>
        </div>

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
            className="flex-1 h-11"
          />
          <Button type="submit" size="lg" disabled={submit.isPending || !url.trim()}>
            {submit.isPending ? "Adding…" : "Process"}
          </Button>
        </form>
        {submit.isError && (
          <p className="text-sm text-destructive">{String(submit.error)}</p>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="eyebrow">
              {showArchived ? "Archived" : "Active"}
            </h2>
            {allJobs.length > 0 && (
              <button
                onClick={() => {
                  if (selected.size === allJobs.length) setSelected(new Set())
                  else setSelected(new Set(allJobs.map((j) => j.id)))
                }}
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                {selected.size === allJobs.length
                  ? `Deselect all (${allJobs.length})`
                  : `Select all (${allJobs.length})`}
              </button>
            )}
          </div>
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
          <div className="sticky top-14 z-20 bg-background/95 backdrop-blur border border-border rounded-md p-2 px-3 flex items-center gap-2 shadow-md">
            <span className="text-sm font-medium">
              {selected.size} selected
            </span>
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
            <h3 className="eyebrow">
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
            <h3 className="eyebrow">
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
          <div className="paper-card p-8 text-center text-sm text-muted-foreground">
            {showArchived
              ? "No archived jobs."
              : "Nothing in flight. Paste a URL above to add a podcast or video."}
          </div>
        )}
      </div>
    </div>
  )
}
