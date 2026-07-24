import { useEffect, useState } from 'react'
import { AuthScreen } from './components/AuthScreen'
import { ToastViewport } from './components/ToastViewport'
import { Shell, type View } from './components/Shell'
import { api } from './lib/api'
import { AgentsPage } from './pages/AgentsPage'
import { Dashboard } from './pages/Dashboard'
import { PipelineBuilder } from './pages/PipelineBuilder'
import { RunsPage } from './pages/RunsPage'
import { TriggersPage } from './pages/TriggersPage'
import { AccessPage } from './pages/AccessPage'
import { DeploymentsPage } from './pages/DeploymentsPage'
import { ProvidersPage } from './pages/ProvidersPage'
import { WorkersPage } from './pages/WorkersPage'
import { McpServersPage } from './pages/McpServersPage'
import { SettingsPage } from './pages/SettingsPage'
import { useI18n } from './i18n'
import type { Agent, User } from './types'

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const { setLocale } = useI18n()
  const [view, setView] = useState<View>('dashboard')
  const [testAgent, setTestAgent] = useState<Agent | undefined>()
  useEffect(() => { api<User>('/auth/me').then(current => { setUser(current); setLocale(current.locale) }).catch(() => setUser(null)) }, [])
  if (user === undefined) return <div className="boot-screen"><span /><p>AGENT FORGE</p></div>
  if (!user) return <AuthScreen onAuthenticated={current => { setUser(current); setLocale(current.locale) }} />
  async function logout() { await api('/auth/logout', { method: 'POST' }); setUser(null) }
  return <><ToastViewport/><Shell user={user} view={view} onView={next=>{if(next==='pipelines')setTestAgent(undefined);setView(next)}} onLogout={logout}>
    {view === 'dashboard' && <Dashboard />}
    {view === 'agents' && <AgentsPage onTest={agent=>{setTestAgent(agent);setView('pipelines')}} />}
    {view === 'pipelines' && <PipelineBuilder key={testAgent?.id??'empty'} initialAgent={testAgent} />}
    {view === 'runs' && <RunsPage />}
    {view === 'triggers' && <TriggersPage />}
    {view === 'deployments' && <DeploymentsPage />}
    {view === 'workers' && <WorkersPage />}
    {view === 'users' && <AccessPage mode="users" />}
    {view === 'groups' && <AccessPage mode="groups" />}
    {view === 'providers' && <ProvidersPage />}
    {view === 'mcp-servers' && <McpServersPage />}
    {view === 'settings' && <SettingsPage user={user} onUser={setUser} />}
  </Shell></>
}
