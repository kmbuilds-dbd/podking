import { useEffect, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { Job } from "@/api"

const TERMINAL = new Set(["done", "failed"])

export function useJobProgress(jobId: string | null) {
  const qc = useQueryClient()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return
    const es = new EventSource(`/events/${jobId}`, { withCredentials: true })
    esRef.current = es

    es.onmessage = (e) => {
      const data = JSON.parse(e.data) as Partial<Job>
      qc.setQueryData<Job>(["jobs", jobId], (prev) =>
        prev ? { ...prev, ...data } : (data as Job)
      )
      qc.setQueryData<Job[]>(["jobs"], (prev) =>
        prev?.map((j) => (j.id === jobId ? { ...j, ...data } : j))
      )
      if (data.status && TERMINAL.has(data.status)) {
        es.close()
        // Refresh summaries list when a job completes
        if (data.status === "done") {
          qc.invalidateQueries({ queryKey: ["summaries"] })
        }
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [jobId, qc])
}
