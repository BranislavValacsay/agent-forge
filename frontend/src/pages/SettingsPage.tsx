import { Languages, Save, Waypoints } from 'lucide-react'
import { useState } from 'react'
import { useI18n, type Locale } from '../i18n'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { User } from '../types'

export function SettingsPage({ user, onUser }: { user: User; onUser: (user: User) => void }) {
  const { locale, setLocale, t } = useI18n()
  const [selected, setSelected] = useState<Locale>(locale)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try {
      const updated = await api<User>('/auth/me/preferences', {
        method: 'PATCH',
        body: JSON.stringify({ locale: selected }),
      })
      setLocale(updated.locale)
      onUser(updated)
      toast(t('settings.saved'), 'success', { kind: 'settings.locale.updated', resource_type: 'user', resource_id: user.id, payload: { locale: updated.locale } })
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : t('settings.saveFailed'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">{t('settings.eyebrow')}</p><h1>{t('settings.title')}</h1><p>{t('settings.description')}</p></div></header>
    <div className="settings-grid">
      <section className="panel settings-card">
        <span className="settings-icon"><Languages /></span>
        <div><h2>{t('settings.languageTitle')}</h2><p>{t('settings.languageDescription')}</p></div>
        <label>{t('settings.languageLabel')}<select value={selected} onChange={event => setSelected(event.target.value as Locale)}><option value="sk">{t('locale.sk')}</option><option value="en">{t('locale.en')}</option></select></label>
        <button className="button primary" disabled={busy || selected === user.locale} onClick={save}><Save size={15}/>{t('common.actions.save')}</button>
      </section>
      <section className="panel settings-card info">
        <span className="settings-icon"><Waypoints /></span>
        <div><h2>{t('settings.extensibleTitle')}</h2><p>{t('settings.extensibleDescription')}</p></div>
      </section>
    </div>
  </div>
}
