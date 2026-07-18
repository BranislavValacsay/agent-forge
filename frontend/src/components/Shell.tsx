import type { ReactNode } from 'react'
import { Activity, Bot, Boxes, ChevronDown, Clock3, Cpu, GitBranch, LayoutDashboard, LogOut, PlugZap, Rocket, ShieldCheck, Users } from 'lucide-react'
import type { User } from '../types'

export type View = 'dashboard' | 'agents' | 'pipelines' | 'runs' | 'triggers' | 'deployments' | 'workers' | 'users' | 'groups' | 'providers' | 'mcp-servers'

const items: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: 'dashboard', label: 'Prehľad', icon: LayoutDashboard },
  { id: 'agents', label: 'Agenti', icon: Bot },
  { id: 'pipelines', label: 'Pipeline', icon: GitBranch },
  { id: 'runs', label: 'Spustenia', icon: Activity },
  { id: 'triggers', label: 'Triggery', icon: Clock3 },
  { id: 'deployments', label: 'Deployment', icon: Rocket },
  { id: 'workers', label: 'Workers', icon: Cpu },
]

export function Shell({ user, view, onView, onLogout, children }: { user: User; view: View; onView: (view: View) => void; onLogout: () => void; children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="logo"><span><Bot size={21} /></span><strong>Agent Forge</strong></div>
        <div className="workspace"><span className="workspace-icon">AF</span><div><small>WORKSPACE</small><strong>Primary</strong></div><ChevronDown size={15} /></div>
        <nav>
          <p>CONTROL</p>
          {items.map(item => <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => onView(item.id)}><item.icon size={17} />{item.label}</button>)}
          <p>ADMINISTRATION</p>
          <button className={view === 'users' ? 'active' : ''} onClick={() => onView('users')}><Users size={17} />Používatelia</button>
          <button className={view === 'groups' ? 'active' : ''} onClick={() => onView('groups')}><ShieldCheck size={17} />Skupiny a ACL</button>
          <button className={view === 'providers' ? 'active' : ''} onClick={() => onView('providers')}><Boxes size={17} />Providery a modely</button>
          <button className={view === 'mcp-servers' ? 'active' : ''} onClick={() => onView('mcp-servers')}><PlugZap size={17} />MCP servery</button>
        </nav>
        <div className="profile">
          <span>{user.display_name.slice(0, 2).toUpperCase()}</span>
          <div><strong>{user.display_name}</strong><small>{user.is_root ? 'ROOT ADMIN' : 'USER'}</small></div>
          <button onClick={onLogout} title="Odhlásiť"><LogOut size={16} /></button>
        </div>
      </aside>
      <section className="main-area">{children}</section>
    </div>
  )
}
