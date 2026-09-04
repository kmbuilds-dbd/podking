import { type FormEvent, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  createTranscription,
  listTranscriptions,
  transcriptionDownloadUrl,
} from "@/api"
import type { Transcription } from "@/api"

const ACCEPTED_EXTENSIONS = new Set([".mp3", ".mp4", ".wav"])

function displayName(transcription: Transcription): string {
  return transcription.description || transcription.original_filename
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function statusClass(status: Transcription["status"]): string {
  if (status === "done") return "text-emerald-700 bg-emerald-100/60"
  if (status === "failed") return "text-destructive bg-destructive/10"
  return "text-amber-800 bg-amber-100/60"
}

function TranscriptionCard({ item }: { item: Transcription }) {
  const active = !["done", "failed"].includes(item.status)
  return (
    <article className="paper-card p-4 space-y-3" aria-label={displayName(item)}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="font-serif text-lg font-semibold tracking-tightest truncate">
            {displayName(item)}
          </h3>
          <p className="text-xs text-muted-foreground truncate" title={item.original_filename}>
            {item.original_filename}
          </p>
        </div>
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 shrink-0 ${statusClass(item.status)}`}
        >
          {item.status}
        </span>
      </div>

      {active && (
        <div className="space-y-1.5">
          <div className="w-full bg-secondary rounded-full h-1 overflow-hidden">
            <div
              className="bg-foreground h-1 rounded-full transition-all"
              style={{ width: `${item.progress_pct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {item.progress_message || "Waiting to start…"}
          </p>
        </div>
      )}

      {item.status === "failed" && item.error && (
        <p className="text-sm text-destructive">{item.error}</p>
      )}

      {item.status === "done" && item.transcript_text && (
        <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded-md bg-secondary/50 p-3 text-sm leading-relaxed font-sans">
          {item.transcript_preview || item.transcript_text}
        </pre>
      )}

      <div className="flex items-center justify-between gap-3 pt-1">
        <span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
        {item.status === "done" && (
          <a
            href={transcriptionDownloadUrl(item.id)}
            download
            className="text-sm font-medium underline underline-offset-4 hover:text-foreground/70"
          >
            Download text
          </a>
        )}
      </div>
    </article>
  )
}

export default function Transcriptions() {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [description, setDescription] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  const history = useQuery({
    queryKey: ["transcriptions"],
    queryFn: listTranscriptions,
    refetchInterval: (historyQuery) =>
      historyQuery.state.data?.some((item) => !["done", "failed"].includes(item.status))
        ? 3000
        : false,
  })

  const submit = useMutation({
    mutationFn: ({ selectedFile, selectedDescription }: { selectedFile: File; selectedDescription: string }) =>
      createTranscription(selectedFile, selectedDescription),
    onSuccess: () => {
      setFile(null)
      setDescription("")
      setFormError(null)
      qc.invalidateQueries({ queryKey: ["transcriptions"] })
    },
  })

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file) {
      setFormError("Choose an MP3, MP4, or WAV file first.")
      return
    }
    setFormError(null)
    submit.mutate({ selectedFile: file, selectedDescription: description.trim() })
  }

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-3xl mx-auto px-6 pt-10 pb-16 space-y-10">
        <div className="space-y-2">
          <p className="eyebrow">Transcriptions</p>
          <h1 className="font-serif text-4xl sm:text-5xl tracking-tightest font-semibold leading-[1.05]">
            Turn a recording into{" "}
            <span className="italic text-muted-foreground">words.</span>
          </h1>
          <p className="text-sm text-muted-foreground max-w-xl">
            Upload an MP3, MP4, or WAV file. ElevenLabs Scribe will transcribe it and keep the result here for download.
          </p>
        </div>

        <form onSubmit={onSubmit} className="paper-card p-5 space-y-5">
          <div className="space-y-2">
            <Label htmlFor="audio-file">Audio file</Label>
            <Input
              id="audio-file"
              type="file"
              accept=".mp3,.mp4,.wav,audio/mpeg,audio/mp4,audio/wav"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null
                const extension = next ? next.name.slice(next.name.lastIndexOf(".")).toLowerCase() : ""
                if (next && !ACCEPTED_EXTENSIONS.has(extension)) {
                  setFile(null)
                  setFormError("Use an MP3, MP4, or WAV file.")
                  return
                }
                setFormError(null)
                setFile(next)
              }}
              disabled={submit.isPending}
            />
            <p className="text-xs text-muted-foreground">Supported formats: MP3, MP4, WAV.</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="transcription-description">
              Description <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Textarea
              id="transcription-description"
              placeholder="e.g. Customer interview from Tuesday"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={submit.isPending}
              maxLength={500}
              rows={3}
            />
          </div>

          {(formError || submit.isError) && (
            <p className="text-sm text-destructive" role="alert">
              {formError || String(submit.error)}
            </p>
          )}

          {submit.isSuccess && !submit.isPending && (
            <p className="text-sm text-emerald-700" role="status">
              Upload queued. Your transcript will appear below.
            </p>
          )}

          <Button type="submit" size="lg" disabled={submit.isPending || !file}>
            {submit.isPending ? "Uploading…" : "Transcribe audio"}
          </Button>
        </form>

        <section className="space-y-3" aria-labelledby="transcription-history-heading">
          <div className="flex items-center justify-between">
            <h2 id="transcription-history-heading" className="eyebrow">Generated history</h2>
            {history.data && history.data.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {history.data.length} file{history.data.length === 1 ? "" : "s"}
              </span>
            )}
          </div>

          {history.isLoading && <p className="text-sm text-muted-foreground">Loading history…</p>}
          {history.isError && <p className="text-sm text-destructive">Could not load transcription history.</p>}
          {!history.isLoading && !history.isError && history.data?.length === 0 && (
            <div className="paper-card p-8 text-center text-sm text-muted-foreground">
              Your generated transcripts will appear here.
            </div>
          )}
          <div className="space-y-3">
            {history.data?.map((item) => <TranscriptionCard key={item.id} item={item} />)}
          </div>
        </section>
      </main>
    </div>
  )
}
