import { Button } from "@/components/ui/button"

export default function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="p-8 rounded-xl border max-w-sm w-full space-y-4 text-center">
        <h1 className="text-2xl font-semibold">podking</h1>
        <p className="text-sm text-muted-foreground">Sign in to continue.</p>
        <Button asChild className="w-full">
          <a href="/auth/login">Continue with Google</a>
        </Button>
      </div>
    </div>
  )
}
