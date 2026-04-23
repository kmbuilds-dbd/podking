import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listSubscriptions,
  createSubscription,
  deleteSubscription,
  patchSubscription,
} from "@/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Subscription } from "@/api"

function SubRow({ sub }: { sub: Subscription }) {
  const qc = useQueryClient()

  const toggle = useMutation({
    mutationFn: () => patchSubscription(sub.id, !sub.active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  })

  const del = useMutation({
    mutationFn: () => deleteSubscription(sub.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  })

  return (
    <div className="flex items-center gap-3 border rounded p-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{sub.title ?? sub.feed_url}</p>
        <p className="text-xs text-muted-foreground">
          {sub.kind === "youtube_channel" ? "YouTube" : "Podcast"} ·{" "}
          {sub.last_checked_at
            ? `checked ${new Date(sub.last_checked_at).toLocaleDateString()}`
            : "never checked"}
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => toggle.mutate()}
        disabled={toggle.isPending}
        className={sub.active ? "" : "opacity-50"}
      >
        {sub.active ? "Active" : "Paused"}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => { if (confirm("Remove subscription?")) del.mutate() }}
        disabled={del.isPending}
        className="text-red-600 hover:text-red-700"
      >
        ×
      </Button>
    </div>
  )
}

export default function Subscriptions() {
  const qc = useQueryClient()
  const [url, setUrl] = useState("")

  const subs = useQuery({ queryKey: ["subscriptions"], queryFn: listSubscriptions })

  const add = useMutation({
    mutationFn: () => createSubscription(url.trim()),
    onSuccess: () => {
      setUrl("")
      qc.invalidateQueries({ queryKey: ["subscriptions"] })
    },
  })

  return (
    <div className="min-h-screen p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Home</Link>
        <h1 className="text-xl font-semibold">Subscriptions</h1>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); add.mutate() }}
      >
        <Input
          placeholder="YouTube channel URL or podcast RSS feed URL…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={add.isPending}
          className="flex-1"
        />
        <Button type="submit" disabled={add.isPending || !url.trim()}>
          {add.isPending ? "Adding…" : "Follow"}
        </Button>
      </form>
      {add.isError && <p className="text-sm text-red-600">{String(add.error)}</p>}

      {subs.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {subs.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">No subscriptions yet.</p>
      )}

      <div className="space-y-2">
        {subs.data?.map((s) => <SubRow key={s.id} sub={s} />)}
      </div>
    </div>
  )
}
