import { Link } from "react-router-dom"
import { useMe } from "@/hooks/useMe"
import { Button } from "@/components/ui/button"

export default function Home() {
  const me = useMe()
  return (
    <div className="min-h-screen p-6 max-w-3xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">podking</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{me.data?.email}</span>
          <Button variant="outline" asChild size="sm">
            <Link to="/settings">Settings</Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              await fetch("/auth/logout", { method: "POST", credentials: "include" })
              window.location.href = "/login"
            }}
          >
            Logout
          </Button>
        </div>
      </header>
      <p className="text-muted-foreground">
        Welcome. Paste URL feature lands in Plan 2.
      </p>
    </div>
  )
}
