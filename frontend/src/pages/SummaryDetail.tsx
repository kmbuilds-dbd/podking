import { useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getSummary, deleteSummary, patchSummaryTags, getTranscript, createResumamarize } from "@/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function SummaryDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [showTranscript, setShowTranscript] = useState(false)
  const [addTagInput, setAddTagInput] = useState("")

  const summary = useQuery({
    queryKey: ["summary", id],
    queryFn: () => getSummary(id!),
    enabled: !!id,
  })

  const transcript = useQuery({
    queryKey: ["transcript", summary.data?.episode.id],
    queryFn: () => getTranscript(summary.data!.episode.id),
    enabled: showTranscript && !!summary.data?.episode.id,
  })

  const del = useMutation({
    mutationFn: () => deleteSummary(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["summaries"] })
      navigate("/")
    },
  })

  const tagMutation = useMutation({
    mutationFn: ({ add, remove }: { add: string[]; remove: string[] }) =>
      patchSummaryTags(id!, add, remove),
    onSuccess: (updated) => {
      qc.setQueryData(["summary", id], updated)
    },
  })

  const resummarize = useMutation({
    mutationFn: () => createResumamarize(summary.data!.episode.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] })
      navigate("/")
    },
  })

  if (summary.isLoading) return <div className="p-6">Loading…</div>
  if (summary.isError) return <div className="p-6 text-red-600">Error loading summary.</div>
  if (!summary.data) return null

  const s = summary.data
  const { tldr, key_points, quotes } = s.content

  const handleAddTag = () => {
    const name = addTagInput.trim().toLowerCase()
    if (!name) return
    tagMutation.mutate({ add: [name], remove: [] })
    setAddTagInput("")
  }

  return (
    <div className="min-h-screen p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Home</Link>
        <div className="flex-1" />
        <Button
          variant="outline"
          size="sm"
          onClick={() => resummarize.mutate()}
          disabled={resummarize.isPending}
        >
          Re-summarize
        </Button>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => { if (confirm("Delete this summary?")) del.mutate() }}
          disabled={del.isPending}
        >
          Delete
        </Button>
      </div>

      <div>
        <h1 className="text-xl font-semibold">{s.episode.title ?? s.episode.source_url}</h1>
        {s.episode.author && (
          <p className="text-sm text-muted-foreground">{s.episode.author}</p>
        )}
      </div>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-1">TL;DR</h2>
        <p>{tldr}</p>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Key Points</h2>
        <ul className="list-disc list-inside space-y-1">
          {key_points.map((pt, i) => <li key={i} className="text-sm">{pt}</li>)}
        </ul>
      </section>

      {quotes.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Quotes</h2>
          <div className="space-y-3">
            {quotes.map((q, i) => (
              <blockquote key={i} className="border-l-4 pl-3 italic text-sm">
                "{q.text}"
                {q.speaker && <footer className="text-xs not-italic text-muted-foreground mt-0.5">— {q.speaker}</footer>}
              </blockquote>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Tags</h2>
        <div className="flex gap-2 flex-wrap items-center">
          {s.tags.map((t) => (
            <span
              key={t.name}
              className={`text-xs rounded px-2 py-1 flex items-center gap-1 ${
                t.source === "llm" ? "bg-secondary" : "bg-blue-100 text-blue-800"
              }`}
            >
              {t.name}
              {t.source === "llm" && <span title="AI suggested" className="opacity-50">✦</span>}
              <button
                onClick={() => tagMutation.mutate({ add: [], remove: [t.name] })}
                className="ml-0.5 opacity-50 hover:opacity-100"
                aria-label={`Remove ${t.name}`}
              >
                ×
              </button>
            </span>
          ))}
          <form
            className="flex gap-1"
            onSubmit={(e) => { e.preventDefault(); handleAddTag() }}
          >
            <Input
              className="h-7 text-xs w-28"
              placeholder="add tag…"
              value={addTagInput}
              onChange={(e) => setAddTagInput(e.target.value)}
            />
            <Button type="submit" size="sm" className="h-7 text-xs px-2">+</Button>
          </form>
        </div>
      </section>

      <section>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowTranscript((v) => !v)}
        >
          {showTranscript ? "Hide transcript" : "Show transcript"}
        </Button>
        {showTranscript && (
          <div className="mt-2 max-h-96 overflow-y-auto border rounded p-3 text-xs text-muted-foreground whitespace-pre-wrap">
            {transcript.isLoading ? "Loading…" : (transcript.data?.text ?? "No transcript available.")}
          </div>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        Summarized {new Date(s.created_at).toLocaleDateString()} · {s.model}
      </p>
    </div>
  )
}
