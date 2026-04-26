import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getFeedUrl, readerUrlFor } from "@/api"

/**
 * Copies a per-summary public reader URL to the clipboard. The user pastes
 * it into ElevenReader / any read-it-later app.
 *
 * Built as a self-contained component so future "Send to..." targets
 * (Pocket, Readwise) can wrap or replace it without touching every place
 * that mounts the button.
 */
export function ListenButton({
  summaryId,
  variant = "card",
}: {
  summaryId: string
  variant?: "card" | "detail"
}) {
  const feed = useQuery({
    queryKey: ["feed-url"],
    queryFn: getFeedUrl,
    staleTime: 5 * 60 * 1000, // token rarely changes
  })

  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 2500)
    return () => clearTimeout(t)
  }, [copied])

  const onClick = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!feed.data) return
    const url = readerUrlFor(feed.data.base_url, summaryId)
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      // Clipboard API blocked — fall back to opening the URL.
      window.open(url, "_blank", "noopener,noreferrer")
    }
  }

  const disabled = feed.isLoading || feed.isError
  const label = copied ? "✓ Copied" : "🎧 Listen"
  const title = copied
    ? "Reader link copied — paste in ElevenReader"
    : "Copy a reader link to paste in ElevenReader (or any reading app)"

  if (variant === "detail") {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        title={title}
        className={`text-sm border rounded px-3 py-1.5 transition-colors ${
          copied
            ? "border-blue-400 bg-blue-50 text-blue-700"
            : "border-neutral-300 hover:bg-accent"
        }`}
      >
        {label}
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`text-xs border rounded px-2 py-0.5 transition-colors ${
        copied
          ? "border-blue-400 bg-blue-50 text-blue-700"
          : "border-neutral-300 hover:bg-accent"
      }`}
    >
      {label}
    </button>
  )
}
