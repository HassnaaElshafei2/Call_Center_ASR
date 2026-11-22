import { StrictMode, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource/poppins/400.css'
import '@fontsource/poppins/500.css'
import '@fontsource/poppins/600.css'
import 'remixicon/fonts/remixicon.css'
import './styles/app.css'
import { AuthProvider, useAuth } from './lib/auth'
import { Shell } from './components/Shell'
import { Skeleton, ToastProvider } from './components/ui'
import Login from './pages/Login'

const HomePage = lazy(() => import('./pages/Home'))
const Overview = lazy(() => import('./pages/Overview'))
const Calls = lazy(() => import('./pages/Calls'))
const CallDetail = lazy(() => import('./pages/CallDetail'))
const Customers = lazy(() => import('./pages/Customers'))
const CustomerDetail = lazy(() => import('./pages/CustomerDetail'))
const Agents = lazy(() => import('./pages/Agents'))
const AgentDetail = lazy(() => import('./pages/AgentDetail'))
const Actions = lazy(() => import('./pages/Actions'))
const Brief = lazy(() => import('./pages/Brief'))
const AskPage = lazy(() => import('./pages/AskPage'))
const Admin = lazy(() => import('./pages/Admin'))

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 20_000 } } })

function Protected({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div style={{ padding: 40 }}><Skeleton h={200} /></div>
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  return <>{children}</>
}

function Landing() {
  const { me, loading } = useAuth()
  if (loading) return <div style={{ padding: 40 }}><Skeleton h={200} /></div>     // wait for the session before deciding
  if (!me) return <Navigate to="/login" replace />
  const first = me.enterprises.length > 1 ? 'all' : me.enterprises[0]?.id ?? 'all'
  return <Navigate to={`/e/${first}/home`} replace />
}

const page = (el: React.ReactNode) => <Suspense fallback={<div className="content"><Skeleton h={320} /></div>}>{el}</Suspense>

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/" element={<Landing />} />
              <Route path="/e/:ent" element={<Protected><Shell /></Protected>}>
                <Route index element={<Navigate to="home" replace />} />
                <Route path="home" element={page(<HomePage />)} />
                <Route path="overview" element={page(<Overview />)} />
                <Route path="calls" element={page(<Calls />)} />
                <Route path="review" element={page(<Calls review />)} />
                <Route path="calls/:id" element={page(<CallDetail />)} />
                <Route path="customers" element={page(<Customers />)} />
                <Route path="customers/:id" element={page(<CustomerDetail />)} />
                <Route path="agents" element={page(<Agents />)} />
                <Route path="agents/:id" element={page(<AgentDetail />)} />
                <Route path="actions" element={page(<Actions />)} />
                <Route path="brief" element={page(<Brief />)} />
                <Route path="ask" element={page(<AskPage />)} />
                <Route path="admin" element={page(<Admin />)} />
              </Route>
              <Route path="*" element={<Landing />} />
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
