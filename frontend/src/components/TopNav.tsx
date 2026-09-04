import { NavLink, Link } from "react-router-dom"
import { useMe } from "@/hooks/useMe"
import { Button } from "@/components/ui/button"

const NAV_LINKS: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "Library", end: true },
  { to: "/jobs", label: "Jobs" },
  { to: "/transcriptions", label: "Transcriptions" },
  { to: "/subscriptions", label: "Subscriptions" },
]

function Wordmark() {
  return (
    <Link
      to="/"
      className="flex items-center gap-2 group"
      aria-label="podking — home"
    >
      <span
        aria-hidden="true"
        className="grid place-items-center w-7 h-7 rounded-md bg-foreground text-background"
      >
        <svg viewBox="0 0 32 32" className="w-4 h-4" fill="none">
          <path
            d="M7.5 10.5 L9.75 6 L12 10.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <path
            d="M13.75 10.5 L16 4 L18.25 10.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <path
            d="M20 10.5 L22.25 6 L24.5 10.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <rect x="8.5" y="12" width="2.5" height="13" rx="1.25" fill="currentColor" />
          <rect x="14.75" y="12" width="2.5" height="16" rx="1.25" fill="currentColor" />
          <rect x="21" y="12" width="2.5" height="13" rx="1.25" fill="currentColor" />
        </svg>
      </span>
      <span className="font-serif text-lg leading-none tracking-tightest font-semibold">
        podking
      </span>
    </Link>
  )
}

export function TopNav() {
  const me = useMe()

  return (
    <header className="border-b border-border/80 bg-background/80 backdrop-blur-sm sticky top-0 z-30">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center gap-6">
        <Wordmark />
        <nav className="flex gap-5 text-sm flex-1">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  "relative py-1 transition-colors",
                  isActive
                    ? "text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  {label}
                  {isActive && (
                    <span
                      aria-hidden="true"
                      className="absolute -bottom-[15px] left-0 right-0 h-px bg-foreground"
                    />
                  )}
                </>
              )}
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
