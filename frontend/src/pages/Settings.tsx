import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  api,
  createPromptStyle,
  deletePromptStyle,
  getFeedUrl,
  patchPromptStyle,
  regenerateFeedUrl,
  type PromptStyle,
} from "@/api"
import { TopNav } from "@/components/TopNav"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

type SettingsResp = {
  system_prompt: string
  prompt_styles: PromptStyle[]
  anthropic_key: { set: boolean }
  elevenlabs_key: { set: boolean }
  voyage_key: { set: boolean }
  tts_voice_a_id: string | null
  tts_voice_b_id: string | null
}

function PromptStyleEditor({
  style,
  onSave,
  onDelete,
  isSaving,
  isDeleting,
}: {
  style: PromptStyle
  onSave: (id: string, label: string, prompt_text: string) => void
  onDelete: (id: string) => void
  isSaving: boolean
  isDeleting: boolean
}) {
  const [label, setLabel] = useState(style.label)
  const [promptText, setPromptText] = useState(style.prompt_text)

  return (
    <div className="space-y-3 rounded-md border p-4">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={`style-label-${style.id}`}>Style label</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          disabled={isDeleting}
          onClick={() => onDelete(style.id)}
        >
          Delete
        </Button>
      </div>
      <Input
        id={`style-label-${style.id}`}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <Textarea
        rows={5}
        value={promptText}
        onChange={(e) => setPromptText(e.target.value)}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={isSaving || !label.trim() || !promptText.trim()}
        onClick={() => onSave(style.id, label, promptText)}
      >
        {isSaving ? "Saving…" : "Save style"}
      </Button>
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const settings = useQuery<SettingsResp>({
    queryKey: ["settings"],
    queryFn: () => api<SettingsResp>("/api/settings"),
  })

  const [prompt, setPrompt] = useState("")
  const [anthropic, setAnthropic] = useState("")
  const [eleven, setEleven] = useState("")
  const [voyage, setVoyage] = useState("")
  const [voiceA, setVoiceA] = useState("")
  const [voiceB, setVoiceB] = useState("")
  const [tokenCopied, setTokenCopied] = useState(false)
  const [newStyleLabel, setNewStyleLabel] = useState("")
  const [newStylePrompt, setNewStylePrompt] = useState("")

  useEffect(() => {
    if (settings.data) {
      setPrompt(settings.data.system_prompt)
      setVoiceA(settings.data.tts_voice_a_id ?? "")
      setVoiceB(settings.data.tts_voice_b_id ?? "")
    }
  }, [settings.data])

  const feed = useQuery({
    queryKey: ["feed-url"],
    queryFn: getFeedUrl,
  })

  const regenerate = useMutation({
    mutationFn: regenerateFeedUrl,
    onSuccess: (data) => {
      qc.setQueryData(["feed-url"], data)
    },
  })

  const save = useMutation({
    mutationFn: (body: Record<string, string>) =>
      api<SettingsResp>("/api/settings", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      setAnthropic("")
      setEleven("")
      setVoyage("")
      qc.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const createStyle = useMutation({
    mutationFn: () => createPromptStyle(newStyleLabel, newStylePrompt),
    onSuccess: () => {
      setNewStyleLabel("")
      setNewStylePrompt("")
      qc.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const updateStyle = useMutation({
    mutationFn: ({ id, label, prompt_text }: { id: string; label: string; prompt_text: string }) =>
      patchPromptStyle(id, { label, prompt_text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  })

  const removeStyle = useMutation({
    mutationFn: deletePromptStyle,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  })

  const keyLabel = (set: boolean, name: string) =>
    set ? `•••• ${name} set` : `${name} not set`

  if (!settings.data)
    return (
      <div className="min-h-screen">
        <TopNav />
        <div className="max-w-2xl mx-auto p-6">Loading…</div>
      </div>
    )

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="max-w-2xl mx-auto px-6 pt-10 pb-16 space-y-8">
        <div className="flex items-end justify-between">
          <div className="space-y-2">
            <p className="eyebrow">Settings</p>
            <h1 className="font-serif text-4xl tracking-tightest font-semibold leading-[1.05]">
              Tune the room.
            </h1>
          </div>
          <Link
            to="/"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← Library
          </Link>
        </div>

      <div className="space-y-3">
        <Label>Analysis style guidance · general</Label>
        <p className="text-xs text-muted-foreground">
          Shape <em>how</em> Claude analyzes the transcript — depth, focus, tone, what to emphasize.
          Output structure is fixed: <code>tldr</code>, <code>key_points</code>, <code>quotes</code>,
          <code> suggested_tags</code>. Don't include format directives or output-shape instructions
          here — they'll be ignored.
        </p>
        <Textarea
          rows={8}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Focus on actionable insights. Surface specific numbers, names, and arguments. Distinguish strong claims from speculation. Prefer dense, substantive bullets over filler."
        />
      </div>

      <div className="space-y-4 border-t pt-6">
        <div>
          <Label>Custom styles</Label>
          <p className="text-xs text-muted-foreground mt-1">
            Create private analysis styles and assign them to subscriptions from their detail page.
          </p>
        </div>
        {settings.data.prompt_styles
          .filter((style) => style.label !== "general")
          .map((style) => (
            <PromptStyleEditor
              key={style.id}
              style={style}
              onSave={(id, label, prompt_text) =>
                updateStyle.mutate({ id, label, prompt_text })
              }
              onDelete={(id) => {
                if (confirm("Delete this style? Assigned subscriptions will use general.")) {
                  removeStyle.mutate(id)
                }
              }}
              isSaving={updateStyle.isPending}
              isDeleting={removeStyle.isPending}
            />
          ))}
        <div className="space-y-3 rounded-md border border-dashed p-4">
          <Label>Add a style</Label>
          <Input
            placeholder="e.g. Executive brief"
            value={newStyleLabel}
            onChange={(e) => setNewStyleLabel(e.target.value)}
          />
          <Textarea
            rows={5}
            placeholder="Focus on decisions, risks, and implications for leaders."
            value={newStylePrompt}
            onChange={(e) => setNewStylePrompt(e.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={
              createStyle.isPending || !newStyleLabel.trim() || !newStylePrompt.trim()
            }
            onClick={() => createStyle.mutate()}
          >
            {createStyle.isPending ? "Adding…" : "Add style"}
          </Button>
          {createStyle.isError && (
            <p className="text-sm text-red-600">Error: {String(createStyle.error)}</p>
          )}
        </div>
      </div>

      <div className="space-y-3 border-t pt-6">
        <Label>Reader links</Label>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Each summary in your library has a public URL anchored to a personal
          token. The 🎧 Listen button on each card copies a per-summary URL —
          paste it into <a className="underline" href="https://elevenreader.io" target="_blank" rel="noreferrer">ElevenReader</a> (or
          any read-it-later app, or your browser's reader mode) to listen to it.
          Anyone with this token can read every summary you have, so treat it
          like a password.
        </p>

        {feed.isLoading && (
          <p className="text-xs text-muted-foreground">Loading…</p>
        )}
        {feed.data && (
          <div className="bg-secondary/50 border rounded p-3 space-y-3 text-xs">
            <div className="space-y-1">
              <p className="uppercase tracking-wide font-semibold text-muted-foreground">
                Token
              </p>
              <div className="flex gap-2 items-center">
                <code className="font-mono flex-1 truncate">{feed.data.token}</code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={async () => {
                    await navigator.clipboard.writeText(feed.data!.token)
                    setTokenCopied(true)
                    setTimeout(() => setTokenCopied(false), 2000)
                  }}
                >
                  {tokenCopied ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
            <div className="space-y-1">
              <p className="uppercase tracking-wide font-semibold text-muted-foreground">
                Base URL
              </p>
              <code className="font-mono text-muted-foreground break-all block">
                {feed.data.base_url}/{`{summary_id}`}.html
              </code>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={regenerate.isPending}
            onClick={() => {
              if (
                confirm(
                  "Regenerate token? Any reader links you've already copied or " +
                    "shared will stop working.",
                )
              ) {
                regenerate.mutate()
              }
            }}
          >
            {regenerate.isPending ? "Regenerating…" : "Regenerate token"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Breaks any links you've already copied.
          </p>
        </div>
      </div>

      <div className="space-y-4 border-t pt-6">
        <div>
          <Label>Anthropic API key</Label>
          <p className="text-xs text-muted-foreground mb-1">
            {keyLabel(settings.data.anthropic_key.set, "Anthropic")}
          </p>
          <Input
            type="password"
            placeholder="sk-ant-…"
            value={anthropic}
            onChange={(e) => setAnthropic(e.target.value)}
          />
        </div>
        <div>
          <Label>ElevenLabs API key</Label>
          <p className="text-xs text-muted-foreground mb-1">
            {keyLabel(settings.data.elevenlabs_key.set, "ElevenLabs")}
          </p>
          <Input
            type="password"
            value={eleven}
            onChange={(e) => setEleven(e.target.value)}
          />
        </div>
        <div>
          <Label>Voyage API key</Label>
          <p className="text-xs text-muted-foreground mb-1">
            {keyLabel(settings.data.voyage_key.set, "Voyage")}
          </p>
          <Input
            type="password"
            value={voyage}
            onChange={(e) => setVoyage(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-4 border-t pt-6">
        <div>
          <Label htmlFor="tts_voice_a">Host A voice ID (optional)</Label>
          <Input
            id="tts_voice_a"
            type="text"
            placeholder="Leave blank to use server default"
            value={voiceA}
            onChange={(e) => setVoiceA(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="tts_voice_b">Host B voice ID (optional)</Label>
          <Input
            id="tts_voice_b"
            type="text"
            placeholder="Leave blank to use server default"
            value={voiceB}
            onChange={(e) => setVoiceB(e.target.value)}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Browse voices at{" "}
          <a
            className="underline"
            href="https://elevenlabs.io/app/voice-library"
            target="_blank"
            rel="noopener noreferrer"
          >
            elevenlabs.io/app/voice-library
          </a>
          {" "}and paste a voice ID. Empty means use the server's default for that host.
        </p>
      </div>

      <Button
        onClick={() => {
          const body: Record<string, string> = { system_prompt: prompt }
          if (anthropic) body.anthropic_api_key = anthropic
          if (eleven) body.elevenlabs_api_key = eleven
          if (voyage) body.voyage_api_key = voyage
          if (voiceA !== (settings.data?.tts_voice_a_id ?? ""))
            body.tts_voice_a_id = voiceA
          if (voiceB !== (settings.data?.tts_voice_b_id ?? ""))
            body.tts_voice_b_id = voiceB
          save.mutate(body)
        }}
        disabled={save.isPending}
      >
        {save.isPending ? "Saving…" : "Save"}
      </Button>
      {save.isError && (
        <p className="text-sm text-red-600">Error: {String(save.error)}</p>
      )}
      </div>
    </div>
  )
}
