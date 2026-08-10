import { useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getSummary, deleteSummary, patchSummaryTags, getTranscript, createResumamarize } from "@/api"
import { TopNav } from "@/components/TopNav"
import { ListenButton } from "@/components/ListenButton"
import { GenerateAudioButton } from "@/components/GenerateAudioButton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

function contentLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

function renderInline(v: unknown): React.ReactNode {
  if (typeof v === "string") return v
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  if (Array.isArray(v))
    return v.map((x, i) => (
      <span key={i}>
        {typeof x === "object" && x !== null ? JSON.stringify(x) : String(x)}
        {i < v.length - 1 ? ", " : ""}
      </span>
    ))
  if (isRecord(v))
    return Object.entries(v)
      .map(([k, x]) => `${contentLabel(k)}: ${String(x)}`)
      .join("; ")
  return String(v)
}

/** Renders arbitrary JSON produced by a custom analysis prompt. */
function RenderContentValue({ value }: { value: unknown }) {
  if (typeof value === "string") {
    return <p className="text-[15px] leading-relaxed">{value}</p>
  }
  if (Array.isArray(value)) {
    return (
      <ol className="space-y-5 counter-reset-key">
        {value.map((item, i) => (
          <li key={i} className="grid grid-cols-[2.5rem_1fr] gap-3">
            <span
              aria-hidden="true"
              className="font-serif text-xl text-muted-foreground pt-0.5"
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            {isRecord(item) ? (
              <div className="space-y-1.5">
                {Object.entries(item)
                  .filter(([, v]) => v !== null && v !== undefined && v !== "")
                  .map(([k, v]) =>
                    k === "take" && typeof v === "string" ? (
                      <span
                        key={k}
                        className="inline-block text-[11px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 bg-foreground/10"
                      >
                        {v}
                      </span>
                    ) : (
                      <p key={k} className="text-[15px] leading-relaxed">
                        <span className="text-muted-foreground text-xs uppercase tracking-wide mr-1.5">
                          {contentLabel(k)}
                        </span>
                        {renderInline(v)}
                      </p>
                    ),
                  )}
              </div>
            ) : (
              <p className="text-[15px] leading-relaxed">
                {typeof item === "string" ? item : String(item)}
              </p>
            )}
          </li>
        ))}
      </ol>
    )
  }
  if (isRecord(value)) {
    return (
      <div className="space-y-1.5">
        {Object.entries(value)
          .filter(([, v]) => v !== null && v !== undefined && v !== "")
          .map(([k, v]) => (
            <p key={k} className="text-[15px] leading-relaxed">
              <span className="text-muted-foreground text-xs uppercase tracking-wide mr-1.5">
                {contentLabel(k)}
              </span>
              {renderInline(v)}
            </p>
          ))}
      </div>
    )
  }
  return null
}

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
  const content = s.content as Record<string, unknown>
  const tldr = typeof content.tldr === "string" ? content.tldr : ""
  // Custom analysis prompts may name the takeaways list differently
  // (e.g. the fantasy style outputs "KEY_POINTS").
  const key_points = Array.isArray(content.key_points)
    ? (content.key_points as unknown[])
    : Array.isArray(content.KEY_POINTS)
      ? (content.KEY_POINTS as unknown[])
      : []
  const quotes = (Array.isArray(content.quotes)
    ? content.quotes
    : []) as { text: string; speaker: string | null }[]
  const extraSections = Object.entries(content).filter(
    ([k]) => !["tldr", "key_points", "KEY_POINTS", "quotes", "suggested_tags"].includes(k),
  )

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
          <GenerateAudioButton summaryId={s.id} variant="detail" />
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
                  <p className="text-[15px] leading-relaxed">
                    {typeof pt === "string" ? pt : String(pt)}
                  </p>
                </li>
              ))}
            </ol>
          </section>

          {/* Extra sections from custom analysis prompts (e.g. PLAYER_NOTES,
              notable_disagreements) — rendered generically so any output
              structure the prompt asks for is visible. */}
          {extraSections.map(([key, value]) => (
            <section key={key} className="space-y-4">
              <p className="eyebrow">{contentLabel(key)}</p>
              <RenderContentValue value={value} />
            </section>
          ))}

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
                    className="w-4 h-4 -mr-1 inline-grid place-items-center rounded-full bg-foreground/10 text-foreground/70 hover:bg-foreground/25 hover:text-foreground transition-colors leading-none"
                    aria-label={`Remove ${t.name}`}
                    title="Remove tag"
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
