import { FormEvent, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, KeyRound, Link2, LoaderCircle, Plus, RefreshCw, Server, Trash2, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { Provider, ProviderModel } from '../types'

type Connection = { ok: boolean; message: string; models: string[] }

export function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [models, setModels] = useState<Record<string, ProviderModel[]>>({})
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [test, setTest] = useState<Connection | null>(null)
  const [error, setError] = useState('')
  const load = () => api<Provider[]>('/providers').then(setProviders)
  useEffect(() => { load().catch(() => undefined) }, [])
  async function connect(provider: Provider) {
    setBusy(provider.id); setError('')
    try {
      await api<Connection>(`/providers/${provider.id}/connect`, { method: 'POST' })
      const found = await api<ProviderModel[]>(`/providers/${provider.id}/models`)
      setModels(current => ({ ...current, [provider.id]: found })); await load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Spojenie zlyhalo') }
    finally { setBusy(null) }
  }
  async function remove(provider: Provider) {
    await api(`/providers/${provider.id}`, { method: 'DELETE' }); await load();toast(`Provider „${provider.name}“ bol odstránený.`,'success',{kind:'provider.deleted',resource_type:'provider',resource_id:provider.id})
  }
  function providerPayload(form: HTMLFormElement) {
    const data = new FormData(form); const kind = String(data.get('kind'))
    const host = String(data.get('host')).replace(/^https?:\/\//, '').replace(/\/$/, '')
    const protocol = String(data.get('protocol')); const port = String(data.get('port')).trim()
    return { name: data.get('name'), kind, base_url: `${protocol}://${host}${port ? `:${port}` : ''}`, api_key: data.get('apiKey') || null, enabled: true }
  }
  async function testConnection(event: React.MouseEvent<HTMLButtonElement>) {
    const form = event.currentTarget.form; if (!form || !form.reportValidity()) return
    setBusy('test'); setTest(null); setError('')
    try { setTest(await api<Connection>('/providers/test', { method: 'POST', body: JSON.stringify(providerPayload(form)) })) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Spojenie zlyhalo') }
    finally { setBusy(null) }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy('save'); setError('')
    try {
      const provider = await api<Provider>('/providers', { method: 'POST', body: JSON.stringify(providerPayload(event.currentTarget)) })
      setCreating(false); setTest(null); await load(); await connect(provider)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Provider sa nepodarilo uložiť') }
    finally { setBusy(null) }
  }
  return <div className="page"><header className="page-header"><div><p className="eyebrow">MODEL REGISTRY</p><h1>Providery a modely</h1><p>Modely sa nezadávajú ručne. Connect načíta skutočný katalóg z provider API.</p></div><button className="button primary" onClick={() => { setCreating(true); setTest(null); setError('') }}><Plus size={16}/>Pridať provider</button></header>
    {error && <div className="form-error page-error">{error}</div>}
    <div className="provider-list">{providers.map(provider => <article className="provider-card" key={provider.id}><div className="provider-mark"><Server/></div><div className="provider-main"><p className="eyebrow">{provider.kind}</p><h2>{provider.name}</h2><code>{provider.base_url}</code><div className="provider-flags"><span><KeyRound size={12}/>{provider.has_api_key ? 'API key uložený' : 'Bez API key'}</span><span>{provider.model_count} modelov</span></div></div><div className="provider-actions"><button className="button ghost" disabled={busy === provider.id} onClick={() => connect(provider)}>{busy === provider.id ? <LoaderCircle className="spin" size={15}/> : <RefreshCw size={15}/>}Connect & sync</button><button className="icon-button danger" onClick={() => remove(provider)}><Trash2 size={15}/></button></div>
      {models[provider.id] && <div className="model-list"><p className="eyebrow">DISCOVERED MODELS</p>{models[provider.id].map(model => <span key={model.id}>{model.display_name}</span>)}{!models[provider.id].length && <small>Provider nevrátil žiadne modely.</small>}</div>}</article>)}
      {!providers.length && <div className="empty-state provider-empty"><Link2 size={25}/><h3>Žiadny model provider</h3><p>Pripoj Ollama alebo OpenAI-compatible API. Platforma následne načíta reálne dostupné modely.</p><button className="button primary" onClick={() => setCreating(true)}>Pridať provider</button></div>}
    </div>
    {creating && <ProviderModal busy={busy} result={test} error={error} onClose={() => setCreating(false)} onSubmit={save} onTest={testConnection}/>}
  </div>
}

function ProviderModal({ busy, result, error, onClose, onSubmit, onTest }: { busy: string|null; result: Connection|null; error: string; onClose:()=>void; onSubmit:(event:FormEvent<HTMLFormElement>)=>void; onTest:(event:React.MouseEvent<HTMLButtonElement>)=>void }) {
  const [kind, setKind] = useState<'ollama'|'openai-compatible'>('ollama')
  const [host, setHost] = useState('host.containers.internal')
  const defaults = useMemo(() => kind === 'ollama' ? { name: 'Local Ollama', port: '11434' } : { name: 'OpenAI compatible', port: '8000' }, [kind])
  return <div className="modal-backdrop" onMouseDown={onClose}><form className="modal provider-modal" onSubmit={onSubmit} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">NEW MODEL PROVIDER</p><h2>Pripojiť provider</h2><div className="provider-kind"><button type="button" className={kind === 'ollama' ? 'active' : ''} onClick={() => { setKind('ollama') }}><strong>Ollama</strong><small>Lokálne Ollama API</small></button><button type="button" className={kind === 'openai-compatible' ? 'active' : ''} onClick={() => setKind('openai-compatible')}><strong>OpenAI compatible</strong><small>vLLM, LM Studio, OpenAI…</small></button></div><input type="hidden" name="kind" value={kind}/>
    <div className="form-grid"><label className="span-2">Názov<input key={defaults.name} name="name" defaultValue={defaults.name} required/></label><label>Protokol<select name="protocol"><option value="http">http</option><option value="https">https</option></select></label><label>IP adresa / hostname<input name="host" required value={host} onChange={event=>setHost(event.target.value)} placeholder="192.168.1.20"/></label><label>Port<input key={defaults.port} name="port" inputMode="numeric" defaultValue={defaults.port} placeholder="11434"/></label><label>API kľúč (nepovinné)<input name="apiKey" type="password" autoComplete="off" placeholder="sk-…"/></label></div>
    <div className="connection-hint"><Server size={14}/><p><strong>Ollama na tom istom Linux hoste:</strong> pri kontajnerovom spustení použi <code>host.containers.internal:11434</code>. Pri vývoji bez kontajnera môžeš použiť <code>127.0.0.1:11434</code>.</p></div>
    {['127.0.0.1','localhost','::1'].includes(host.trim().toLowerCase()) && <div className="connection-result warning"><XCircle size={17}/><div><strong>Pozor na kontajnerový loopback</strong><p>Ak Agent Forge beží cez Compose, táto adresa smeruje do API kontajnera. Použi <code>host.containers.internal</code>; Ollama zároveň musí počúvať na <code>0.0.0.0:11434</code>.</p></div></div>}
    {result && <div className="connection-result success"><CheckCircle2 size={17}/><div><strong>Spojenie funguje</strong><p>{result.models.length ? `Nájdené modely: ${result.models.join(', ')}` : 'Provider nevrátil žiadne modely.'}</p></div></div>}
    {error && <div className="connection-result failed"><XCircle size={17}/><div><strong>Spojenie zlyhalo</strong><p>{error}</p></div></div>}
    <div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Zrušiť</button><button type="button" className="button ghost" onClick={onTest} disabled={busy === 'test'}>{busy === 'test' ? <LoaderCircle className="spin" size={15}/> : <Link2 size={15}/>}Overiť spojenie</button><button className="button primary" disabled={busy === 'save'}>Uložiť a synchronizovať</button></div></form></div>
}
