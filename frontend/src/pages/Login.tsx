import { Button } from "@/components/ui/button"

export default function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="paper-card p-10 max-w-sm w-full space-y-6 text-center">
        <div className="flex justify-center">
          <span
            aria-hidden="true"
            className="grid place-items-center w-12 h-12 rounded-lg bg-foreground text-background"
          >
            <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none">
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
        </div>
        <div className="space-y-1">
          <h1 className="font-serif text-3xl tracking-tightest font-semibold">
            podking
          </h1>
          <p className="text-sm text-muted-foreground italic font-serif">
            Listen later, smarter.
          </p>
        </div>
        <Button asChild className="w-full" size="lg">
          <a href="/auth/login">Continue with Google</a>
        </Button>
      </div>
    </div>
  )
}
