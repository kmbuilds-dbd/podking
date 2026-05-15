import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  generateSummaryAudio,
  getJob,
  listAudioEpisodes,
  type AudioEpisode,
  type Job,
} from "@/api"
import { useJobProgress } from "@/hooks/useJobProgress"
import { useMe } from "@/hooks/useMe"

/**
 * Per-summary control that:
 *  - shows "Generate audio" when no live AudioEpisode exists
 *  - shows progress while a tts job is in-flight (driven by SSE in useJobProgress)
 *  - shows a "▶ Listen / Regenerate" pair once an episode is published
 *
 * The Listen link points at the published_url (GitHub Pages MP3). podking
 * does not serve audio itself.
 */
export function GenerateAudioButton({
  summaryId,
  variant = "card",
}: {
  summaryId: string
  variant?: "card" | "detail"
}) {
  const me = useMe()
  const qc = useQueryClient()

  const audioEnabled = !!me.data?.audio_enabled

  const audio = useQuery({
    queryKey: ["audio_episodes"],
    queryFn: listAudioEpisodes,
    enabled: audioEnabled,
  })
  const live: AudioEpisode | undefined = (audio.data || []).find(
    (a) => a.summary_id === summaryId,
  )

  const [activeJobId, setActiveJobId] = useState<string | null>(null)

  // SSE side-effect: pushes Job updates into ["jobs", activeJobId].
  useJobProgress(activeJobId)

  // Bootstrap the job query with the initial status so the SSE updates
  // have something to merge into.
  const jobQuery = useQuery<Job>({
    queryKey: ["jobs", activeJobId],
    queryFn: () => getJob(activeJobId!),
    enabled: !!activeJobId,
  })
  const job = jobQuery.data

  // When the job reaches a terminal state, refresh the audio_episodes list
  // (the new row was committed during the publishing stage), then clear the
  // active jobId so the button transitions back to a settled state.
  useEffect(() => {
    if (!activeJobId || !job) return
    if (job.status === "done") {
      qc.invalidateQueries({ queryKey: ["audio_episodes"] })
      setActiveJobId(null)
    } else if (job.status === "failed") {
      // Leave activeJobId set so the failure state is rendered; the user
      // clears it by clicking "Retry".
    }
  }, [activeJobId, job, qc])

  const mutation = useMutation({
    mutationFn: (regenerate: boolean) =>
      generateSummaryAudio(summaryId, regenerate),
    onSuccess: (data) => setActiveJobId(data.job_id),
  })

  if (!audioEnabled) return null

  const buttonCls =
    variant === "card"
      ? "text-xs border rounded px-2 py-0.5 transition-colors border-neutral-300 hover:bg-accent"
      : "text-sm border rounded px-3 py-1.5 transition-colors border-neutral-300 hover:bg-accent"

  // In-flight job
  if (activeJobId && job && job.status !== "done" && job.status !== "failed") {
    return (
      <button type="button" disabled className={buttonCls} title="Generating…">
        ⏳ {job.progress_message || "Generating…"} ({job.progress_pct}%)
      </button>
    )
  }

  // Failed job — let the user retry
  if (activeJobId && job?.status === "failed") {
    return (
      <button
        type="button"
        className={buttonCls}
        title={job.error || "Failed"}
        onClick={() => {
          setActiveJobId(null)
          mutation.mutate(true)
        }}
      >
        ⚠ Failed — retry
      </button>
    )
  }

  // Published — show Listen + Regenerate
  if (live?.published_url) {
    return (
      <span className="inline-flex items-center gap-1">
        <a
          href={live.published_url}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonCls}
          title="Open the generated episode in a new tab"
        >
          ▶ Listen
        </a>
        <button
          type="button"
          className={buttonCls}
          title="Regenerate this episode"
          onClick={() => mutation.mutate(true)}
        >
          ⟲ Regenerate
        </button>
      </span>
    )
  }

  // Default — no audio yet
  return (
    <button
      type="button"
      className={buttonCls}
      title="Generate a two-host podcast episode from this summary"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate(false)}
    >
      🎙 Generate audio
    </button>
  )
}
