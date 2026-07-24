import { FormEvent, useState } from 'react'
import { Bot, LockKeyhole, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { User } from '../types'
import { useI18n } from '../i18n'

export function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const { locale, setLocale, t } = useI18n()
  const [register, setRegister] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      const user = await api<User>(register ? '/auth/register' : '/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: data.get('email'),
          password: data.get('password'),
          ...(register ? { display_name: data.get('displayName'), locale } : {}),
        }),
      })
      onAuthenticated(user)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('auth.failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand">
        <div className="brand-mark"><Bot size={27} /></div>
        <p className="eyebrow">{t('auth.controlPlane')}</p>
        <h1>{t('auth.hero')}<br /><span>{t('auth.heroAccent')}</span></h1>
        <p className="auth-copy">{t('auth.copy')}</p>
        <div className="signal-line"><span /><span /><span /><span /></div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-icon"><LockKeyhole size={20} /></div>
          <div className="auth-language"><button className={locale==='sk'?'active':''} onClick={()=>setLocale('sk')}>SK</button><button className={locale==='en'?'active':''} onClick={()=>setLocale('en')}>EN</button></div>
          <p className="eyebrow">{register ? t('auth.bootstrap') : t('auth.welcomeBack')}</p>
          <h2>{register ? t('auth.createRoot') : t('auth.signIn')}</h2>
          <p>{register ? t('auth.rootHint') : t('auth.signInHint')}</p>
          <form onSubmit={submit}>
            {register && <label>{t('auth.displayName')}<input required name="displayName" minLength={2} placeholder="Branislav" /></label>}
            <label>E-mail<input required name="email" type="email" placeholder="admin@example.com" /></label>
            <label>{t('auth.password')}<input required name="password" type="password" minLength={10} placeholder={t('auth.passwordHint')} /></label>
            {error && <div className="form-error">{error}</div>}
            <button className="button primary wide" disabled={busy}>{busy ? t('auth.working') : register ? t('auth.initialize') : t('auth.signIn')} <Sparkles size={16} /></button>
          </form>
          <button className="text-button" onClick={() => setRegister(!register)}>{register ? t('auth.hasAccount') : t('auth.createAccount')}</button>
        </div>
      </section>
    </main>
  )
}
