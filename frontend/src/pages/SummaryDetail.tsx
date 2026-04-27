import { useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getSummary, deleteSummary, patchSummaryTags, getTranscript, createResumamarize } from "@/api"
import { TopNav } from "@/components/TopNav"
import { ListenButton } from "@/components/ListenButton"
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

  if (summary.isLoading)
    return (
      <div className="min-h-screen">
        <TopNav />
        <div className="max-w-2xl mx-auto p-6 text-sm text-muted-foreground">
          Loading…
        </div>
      </div>
    )
  if (summary.isError)
    return (
      <div className="min-h-screen">
        <TopNav />
        <div className="max-w-2xl mx-auto p-6 text-sm text-destructive">
          Error loading summary.
        </div>
      </div>
    )
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
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-2xl mx-auto px-6 pt-10 pb-16">
        {/* Action row */}
        <div className="flex items-center gap-2 mb-8">
          <div className="flex-1" />
          <ListenButton summaryId={s.id} variant="detail" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => resummarize.mutate()}
            disabled={resummarize.isPending}
          >
            Re-summarize
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (confirm("Delete this summary?")) del.mutate()
            }}
            disabled={del.isPending}
            className="text-muted-foreground hover:text-destructive"
            title="Delete summary"
          >
            Delete
          </Button>
        </div>

        <article className="space-y-10">
          {/* Title block */}
          <header className="space-y-3">
            <h1 className="font-serif text-3xl sm:text-4xl leading-[1.1] tracking-tightest font-semibold">
              {s.episode.title ?? s.episode.source_url}
            </h1>
            {s.episode.author && (
              <p className="text-base text-muted-foreground">
                {s.episode.author}
              </p>
            )}
          </header>

          {/* TL;DR — pulled out as a lede paragraph in the body serif. */}
          <section className="border-l-2 border-foreground/20 pl-5">
            <p className="eyebrow mb-2">TL;DR</p>
            <p className="font-serif text-lg leading-relaxed text-foreground/90">
              {tldr}
            </p>
          </section>

          {/* Key takeaways */}
          <section className="space-y-4">
            <p className="eyebrow">Key takeaways</p>
            <ol className="space-y-5 counter-reset-key">
              {key_points.map((pt, i) => (
                <li key={i} className="grid grid-cols-[2.5rem_1fr] gap-3">
                  <span
                    aria-hidden="true"
                    className="font-serif text-xl text-muted-foreground pt-0.5"
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <p className="text-[15px] leading-relaxed">{pt}</p>
                </li>
              ))}
            </ol>
          </section>

          {/* Quotes */}
          {quotes.length > 0 && (
            <section className="space-y-4">
              <p className="eyebrow">Notable quotes</p>
              <div className="space-y-5">
                {quotes.map((q, i) => (
                  <blockquote
                    key={i}
                    className="border-l-2 border-foreground/30 pl-5 py-1"
                  >
                    <p className="font-serif italic text-lg leading-relaxed">
                      &ldquo;{q.text}&rdquo;
                    </p>
                    {q.speaker && (
                      <footer className="not-italic text-sm text-muted-foreground mt-2">
                        — {q.speaker}
                      </footer>
                    )}
                  </blockquote>
                ))}
              </div>
            </section>
          )}

          {/* Tags */}
          <section className="space-y-3">
            <p className="eyebrow">Tags</p>
            <div className="flex gap-1.5 flex-wrap items-center">
              {s.tags.map((t) => (
                <span
                  key={t.name}
                  className={`text-xs rounded-full px-2.5 py-1 inline-flex items-center gap-1.5 ${
                    t.source === "llm"
                      ? "bg-secondary/70 text-secondary-foreground"
                      : "bg-foreground/8 text-foreground border border-foreground/15"
                  }`}
                >
                  {t.source === "llm" && (
                    <span title="AI suggested" className="opacity-40 text-[10px]">
                      ✦
                    </span>
                  )}
                  {t.name}
                  <button
                    onClick={() =>
                      tagMutation.mutate({ add: [], remove: [t.name] })
                    }
                    className="opacity-40 hover:opacity-100 -mr-1 transition-opacity"
                    aria-label={`Remove ${t.name}`}
                  >
                    ×
                  </button>
                </span>
              ))}
              <form
                className="flex gap-1 items-center"
                onSubmit={(e) => {
                  e.preventDefault()
                  handleAddTag()
                }}
              >
                <Input
                  className="h-7 text-xs w-32 rounded-full"
                  placeholder="add tag…"
                  value={addTagInput}
                  onChange={(e) => setAddTagInput(e.target.value)}
                />
                <Button
                  type="submit"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                >
                  +
                </Button>
              </form>
            </div>
          </section>

          {/* Transcript */}
          <section className="border-t border-border pt-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowTranscript((v) => !v)}
              className="text-muted-foreground -ml-3"
            >
              {showTranscript ? "Hide transcript" : "Show full transcript"}
            </Button>
            {showTranscript && (
              <div className="mt-3 max-h-96 overflow-y-auto border border-border/80 rounded-md p-4 text-[13px] leading-relaxed text-muted-foreground whitespace-pre-wrap bg-secondary/30">
                {transcript.isLoading
                  ? "Loading…"
                  : transcript.data?.text ?? "No transcript available."}
              </div>
            )}
          </section>

          <p className="text-xs text-muted-foreground border-t border-border pt-4">
            Summarized {new Date(s.created_at).toLocaleDateString()} ·{" "}
            <span className="font-mono">{s.model}</span>
          </p>
        </article>
      </div>
    </div>
  )
}
