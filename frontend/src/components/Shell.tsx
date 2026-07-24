import type { ReactNode } from 'react'
import { Activity, Bot, Boxes, ChevronDown, Clock3, Cpu, GitBranch, Languages, LayoutDashboard, LogOut, PlugZap, Rocket, ShieldCheck, Users } from 'lucide-react'
import type { User } from '../types'
import { useI18n } from '../i18n'

export type View = 'dashboard' | 'agents' | 'pipelines' | 'runs' | 'triggers' | 'deployments' | 'workers' | 'users' | 'groups' | 'providers' | 'mcp-servers' | 'settings'

const items: Array<{ id: View; label: Parameters<ReturnType<typeof useI18n>['t']>[0]; icon: typeof Activity }> = [
  { id: 'dashboard', label: 'nav.dashboard', icon: LayoutDashboard },
  { id: 'agents', label: 'nav.agents', icon: Bot },
  { id: 'pipelines', label: 'nav.pipelines', icon: GitBranch },
  { id: 'runs', label: 'nav.runs', icon: Activity },
  { id: 'triggers', label: 'nav.triggers', icon: Clock3 },
  { id: 'deployments', label: 'nav.deployments', icon: Rocket },
  { id: 'workers', label: 'nav.workers', icon: Cpu },
]

export function Shell({ user, view, onView, onLogout, children }: { user: User; view: View; onView: (view: View) => void; onLogout: () => void; children: ReactNode }) {
  const { t } = useI18n()
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="logo"><span><Bot size={21} /></span><strong>Agent Forge</strong></div>
        <div className="workspace"><span className="workspace-icon">AF</span><div><small>WORKSPACE</small><strong>Primary</strong></div><ChevronDown size={15} /></div>
        <nav>
          <p>{t('nav.control')}</p>
          {items.map(item => <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => onView(item.id)}><item.icon size={17} />{t(item.label)}</button>)}
          <p>{t('nav.administration')}</p>
          <button className={view === 'users' ? 'active' : ''} onClick={() => onView('users')}><Users size={17} />{t('nav.users')}</button>
          <button className={view === 'groups' ? 'active' : ''} onClick={() => onView('groups')}><ShieldCheck size={17} />{t('nav.groups')}</button>
          <button className={view === 'providers' ? 'active' : ''} onClick={() => onView('providers')}><Boxes size={17} />{t('nav.providers')}</button>
          <button className={view === 'mcp-servers' ? 'active' : ''} onClick={() => onView('mcp-servers')}><PlugZap size={17} />{t('nav.mcpServers')}</button>
          <button className={view === 'settings' ? 'active' : ''} onClick={() => onView('settings')}><Languages size={17} />{t('nav.settings')}</button>
        </nav>
        <div className="profile">
          <span>{user.display_name.slice(0, 2).toUpperCase()}</span>
          <div><strong>{user.display_name}</strong><small>{user.is_root ? 'ROOT ADMIN' : t('nav.user').toUpperCase()}</small></div>
          <button onClick={onLogout} title={t('nav.logout')}><LogOut size={16} /></button>
        </div>
      </aside>
      <section className="main-area">{children}</section>
    </div>
  )
}
