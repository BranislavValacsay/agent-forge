import { FormEvent, useEffect, useState } from 'react'
import { Plus, ShieldCheck, UserRound, Users } from 'lucide-react'
import { api } from '../lib/api'
import type { AdminUser, Group } from '../types'

export function AccessPage({ mode }: { mode: 'users' | 'groups' }) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [creating, setCreating] = useState(false)
  const load = () => mode === 'users' ? api<AdminUser[]>('/users').then(setUsers) : api<Group[]>('/groups').then(setGroups)
  useEffect(() => { load().catch(() => undefined) }, [mode])
  async function createGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget)
    await api('/groups', { method: 'POST', body: JSON.stringify({ name: data.get('name'), description: data.get('description') }) })
    setCreating(false); load()
  }
  return <div className="page"><header className="page-header"><div><p className="eyebrow">IDENTITY & ACCESS</p><h1>{mode === 'users' ? 'Používatelia' : 'Skupiny a ACL'}</h1><p>{mode === 'users' ? 'Účty s prístupom do platformy.' : 'Jednoduché skupiny používané pri zdieľaní agentov a pipeline.'}</p></div>{mode === 'groups' && <button className="button primary" onClick={() => setCreating(true)}><Plus size={16}/>Nová skupina</button>}</header>
    <section className="panel data-table"><div className="data-row head"><span>NÁZOV</span><span>{mode === 'users' ? 'E-MAIL' : 'POPIS'}</span><span>ROLA / VLASTNÍK</span><span>STAV</span></div>
      {mode === 'users' ? users.map(user => <div className="data-row" key={user.id}><span><UserRound size={16}/><strong>{user.display_name}</strong></span><span>{user.email}</span><span>{user.is_root ? 'ROOT' : 'USER'}</span><span className="status-pill">{user.is_active ? 'ACTIVE' : 'DISABLED'}</span></div>) : groups.map(group => <div className="data-row" key={group.id}><span><Users size={16}/><strong>{group.name}</strong></span><span>{group.description || 'Bez popisu'}</span><span>{group.manager_id.slice(0,8)}</span><span className="status-pill"><ShieldCheck size={12}/>ACL GROUP</span></div>)}
      {((mode === 'users' && !users.length) || (mode === 'groups' && !groups.length)) && <div className="table-empty">Žiadne záznamy.</div>}
    </section>
    {creating && <div className="modal-backdrop" onMouseDown={() => setCreating(false)}><form className="modal compact" onSubmit={createGroup} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">NEW ACL GROUP</p><h2>Vytvoriť skupinu</h2><label>Názov<input name="name" required placeholder="engineering"/></label><label>Popis<textarea name="description" placeholder="Členovia a účel skupiny"/></label><div className="modal-actions"><button type="button" className="button ghost" onClick={() => setCreating(false)}>Zrušiť</button><button className="button primary">Vytvoriť</button></div></form></div>}
  </div>
}
