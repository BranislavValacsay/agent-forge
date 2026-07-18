import { FormEvent, useState } from 'react'
import { Bot, LockKeyhole, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { User } from '../types'

export function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
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
          ...(register ? { display_name: data.get('displayName') } : {}),
        }),
      })
      onAuthenticated(user)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Prihlásenie zlyhalo')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand">
        <div className="brand-mark"><Bot size={27} /></div>
        <p className="eyebrow">AGENT FORGE / CONTROL PLANE</p>
        <h1>Vytváraj agentov.<br /><span>Spájaj ich do práce.</span></h1>
        <p className="auth-copy">Jedno miesto na návrh, nasadenie a sledovanie AI aj script agentov — lokálne aj v clustri.</p>
        <div className="signal-line"><span /><span /><span /><span /></div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-icon"><LockKeyhole size={20} /></div>
          <p className="eyebrow">{register ? 'BOOTSTRAP' : 'WELCOME BACK'}</p>
          <h2>{register ? 'Vytvor root účet' : 'Prihlásenie'}</h2>
          <p>{register ? 'Prvý používateľ sa automaticky stane správcom platformy.' : 'Pokračuj do svojho pracovného priestoru.'}</p>
          <form onSubmit={submit}>
            {register && <label>Meno<input required name="displayName" minLength={2} placeholder="Branislav" /></label>}
            <label>E-mail<input required name="email" type="email" placeholder="admin@example.com" /></label>
            <label>Heslo<input required name="password" type="password" minLength={10} placeholder="Minimálne 10 znakov" /></label>
            {error && <div className="form-error">{error}</div>}
            <button className="button primary wide" disabled={busy}>{busy ? 'Pracujem…' : register ? 'Inicializovať platformu' : 'Prihlásiť sa'} <Sparkles size={16} /></button>
          </form>
          <button className="text-button" onClick={() => setRegister(!register)}>{register ? 'Účet už existuje? Prihlásiť sa' : 'Vytvoriť účet'}</button>
        </div>
      </section>
    </main>
  )
}
