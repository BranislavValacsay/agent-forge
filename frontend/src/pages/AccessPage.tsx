import { FormEvent, useEffect, useState } from 'react'
import { Plus, ShieldCheck, UserRound, Users } from 'lucide-react'
import { api } from '../lib/api'
import type { AdminUser, Group } from '../types'
import { translateStatus, useI18n } from '../i18n'

export function AccessPage({ mode }: { mode: 'users' | 'groups' }) {
  const {t}=useI18n()
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
  return <div className="page"><header className="page-header"><div><p className="eyebrow">{t('access.eyebrow')}</p><h1>{mode === 'users' ? t('access.usersTitle') : t('access.groupsTitle')}</h1><p>{mode === 'users' ? t('access.usersDescription') : t('access.groupsDescription')}</p></div>{mode === 'groups' && <button className="button primary" onClick={() => setCreating(true)}><Plus size={16}/>{t('access.newGroup')}</button>}</header>
    <section className="panel data-table"><div className="data-row head"><span>{t('common.fields.name').toUpperCase()}</span><span>{mode === 'users' ? t('common.fields.email').toUpperCase() : t('common.fields.description').toUpperCase()}</span><span>{t('access.ownerRole').toUpperCase()}</span><span>{t('common.fields.status').toUpperCase()}</span></div>
      {mode === 'users' ? users.map(user => <div className="data-row" key={user.id}><span><UserRound size={16}/><strong>{user.display_name}</strong></span><span>{user.email}</span><span>{user.is_root ? 'ROOT' : t('nav.user').toUpperCase()}</span><span className="status-pill">{translateStatus(user.is_active ? 'active' : 'disabled')}</span></div>) : groups.map(group => <div className="data-row" key={group.id}><span><Users size={16}/><strong>{group.name}</strong></span><span>{group.description || t('access.noDescription')}</span><span>{group.manager_id.slice(0,8)}</span><span className="status-pill"><ShieldCheck size={12}/>{t('access.aclGroup')}</span></div>)}
      {((mode === 'users' && !users.length) || (mode === 'groups' && !groups.length)) && <div className="table-empty">{t('access.noRecords')}</div>}
    </section>
    {creating && <div className="modal-backdrop" onMouseDown={() => setCreating(false)}><form className="modal compact" onSubmit={createGroup} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">{t('access.newGroup')}</p><h2>{t('access.createGroup')}</h2><label>{t('common.fields.name')}<input name="name" required placeholder="engineering"/></label><label>{t('common.fields.description')}<textarea name="description" placeholder={t('access.groupDescriptionPlaceholder')}/></label><div className="modal-actions"><button type="button" className="button ghost" onClick={() => setCreating(false)}>{t('common.actions.cancel')}</button><button className="button primary">{t('common.actions.create')}</button></div></form></div>}
  </div>
}
