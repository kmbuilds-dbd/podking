import { NavLink, Link } from "react-router-dom"
import { useMe } from "@/hooks/useMe"
import { Button } from "@/components/ui/button"

const NAV_LINKS: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "Library", end: true },
  { to: "/jobs", label: "Jobs" },
  { to: "/search", label: "Search" },
  { to: "/subscriptions", label: "Subscriptions" },
]

export function TopNav() {
  const me = useMe()

  return (
    <header className="border-b">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center gap-6">
        <Link to="/" className="text-base font-semibold">
          podking
        </Link>
        <nav className="flex gap-4 text-sm flex-1">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                isActive
                  ? "text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground hidden sm:inline">
            {me.data?.email}
          </span>
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
      </div>
    </header>
  )
}
