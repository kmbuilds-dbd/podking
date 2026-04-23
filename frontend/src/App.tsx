import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { useMe } from "@/hooks/useMe"
import { UnauthenticatedError } from "@/api"
import Login from "@/pages/Login"
import Home from "@/pages/Home"
import Settings from "@/pages/Settings"
import SummaryDetail from "@/pages/SummaryDetail"
import Search from "@/pages/Search"
import Subscriptions from "@/pages/Subscriptions"

function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe()
  if (me.isLoading) return <div className="p-6">Loading…</div>
  if (me.error instanceof UnauthenticatedError) return <Navigate to="/login" replace />
  if (me.error) return <div className="p-6 text-red-600">Error: {String(me.error)}</div>
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
      <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
      <Route path="/summary/:id" element={<RequireAuth><SummaryDetail /></RequireAuth>} />
      <Route path="/search" element={<RequireAuth><Search /></RequireAuth>} />
      <Route path="/subscriptions" element={<RequireAuth><Subscriptions /></RequireAuth>} />
    </Routes>
  )
}
