import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

type SettingsResp = {
  system_prompt: string
  anthropic_key: { set: boolean }
  elevenlabs_key: { set: boolean }
  voyage_key: { set: boolean }
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

  useEffect(() => {
    if (settings.data) setPrompt(settings.data.system_prompt)
  }, [settings.data])

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

  if (!settings.data) return <div className="p-6">Loading…</div>

  const keyLabel = (set: boolean, name: string) =>
    set ? `•••• ${name} set` : `${name} not set`

  return (
    <div className="min-h-screen p-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>

      <div className="space-y-2">
        <Label>System prompt</Label>
        <Textarea
          rows={8}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="You are a meticulous note-taker. Summarize as TL;DR, 3–5 key points, and notable quotes."
        />
      </div>

      <div className="space-y-4">
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

      <Button
        onClick={() => {
          const body: Record<string, string> = { system_prompt: prompt }
          if (anthropic) body.anthropic_api_key = anthropic
          if (eleven) body.elevenlabs_api_key = eleven
          if (voyage) body.voyage_api_key = voyage
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
  )
}
