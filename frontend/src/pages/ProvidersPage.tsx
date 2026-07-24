import { FormEvent, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, KeyRound, Link2, LoaderCircle, Plus, RefreshCw, Server, Trash2, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { Provider, ProviderModel } from '../types'
import { useI18n } from '../i18n'

type Connection = { ok: boolean; message: string; models: string[] }

export function ProvidersPage() {
  const {t}=useI18n()
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('providers.connectionFailed')) }
    finally { setBusy(null) }
  }
  async function remove(provider: Provider) {
    await api(`/providers/${provider.id}`, { method: 'DELETE' }); await load();toast(t('providers.deleted',{name:provider.name}),'success',{kind:'provider.deleted',resource_type:'provider',resource_id:provider.id})
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
    catch (reason) { setError(reason instanceof Error ? reason.message : t('providers.connectionFailed')) }
    finally { setBusy(null) }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy('save'); setError('')
    try {
      const provider = await api<Provider>('/providers', { method: 'POST', body: JSON.stringify(providerPayload(event.currentTarget)) })
      setCreating(false); setTest(null); await load(); await connect(provider)
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('providers.saveFailed')) }
    finally { setBusy(null) }
  }
  return <div className="page"><header className="page-header"><div><p className="eyebrow">{t('providers.eyebrow')}</p><h1>{t('providers.title')}</h1><p>{t('providers.description')}</p></div><button className="button primary" onClick={() => { setCreating(true); setTest(null); setError('') }}><Plus size={16}/>{t('providers.add')}</button></header>
    {error && <div className="form-error page-error">{error}</div>}
    <div className="provider-list">{providers.map(provider => <article className="provider-card" key={provider.id}><div className="provider-mark"><Server/></div><div className="provider-main"><p className="eyebrow">{provider.kind}</p><h2>{provider.name}</h2><code>{provider.base_url}</code><div className="provider-flags"><span><KeyRound size={12}/>{provider.has_api_key ? t('providers.apiKeySaved') : t('providers.noApiKey')}</span><span>{t('providers.models',{count:provider.model_count})}</span></div></div><div className="provider-actions"><button className="button ghost" disabled={busy === provider.id} onClick={() => connect(provider)}>{busy === provider.id ? <LoaderCircle className="spin" size={15}/> : <RefreshCw size={15}/>} {t('common.actions.connect')}</button><button className="icon-button danger" title={t('common.actions.delete')} onClick={() => remove(provider)}><Trash2 size={15}/></button></div>
      {models[provider.id] && <div className="model-list"><p className="eyebrow">{t('providers.discoveredModels')}</p>{models[provider.id].map(model => <span key={model.id}>{model.display_name}</span>)}{!models[provider.id].length && <small>{t('providers.noModels')}</small>}</div>}</article>)}
      {!providers.length && <div className="empty-state provider-empty"><Link2 size={25}/><h3>{t('providers.emptyTitle')}</h3><p>{t('providers.emptyDescription')}</p><button className="button primary" onClick={() => setCreating(true)}>{t('providers.add')}</button></div>}
    </div>
    {creating && <ProviderModal busy={busy} result={test} error={error} onClose={() => setCreating(false)} onSubmit={save} onTest={testConnection}/>}
  </div>
}

function ProviderModal({ busy, result, error, onClose, onSubmit, onTest }: { busy: string|null; result: Connection|null; error: string; onClose:()=>void; onSubmit:(event:FormEvent<HTMLFormElement>)=>void; onTest:(event:React.MouseEvent<HTMLButtonElement>)=>void }) {
  const {t}=useI18n()
  const [kind, setKind] = useState<'ollama'|'openai-compatible'>('ollama')
  const [host, setHost] = useState('host.containers.internal')
  const defaults = useMemo(() => kind === 'ollama' ? { name: 'Local Ollama', port: '11434' } : { name: 'OpenAI compatible', port: '8000' }, [kind])
  return <div className="modal-backdrop" onMouseDown={onClose}><form className="modal provider-modal" onSubmit={onSubmit} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">{t('providers.newEyebrow')}</p><h2>{t('providers.connectTitle')}</h2><div className="provider-kind"><button type="button" className={kind === 'ollama' ? 'active' : ''} onClick={() => { setKind('ollama') }}><strong>Ollama</strong><small>{t('providers.ollamaLocal')}</small></button><button type="button" className={kind === 'openai-compatible' ? 'active' : ''} onClick={() => setKind('openai-compatible')}><strong>OpenAI compatible</strong><small>{t('providers.openaiHint')}</small></button></div><input type="hidden" name="kind" value={kind}/>
    <div className="form-grid"><label className="span-2">{t('common.fields.name')}<input key={defaults.name} name="name" defaultValue={defaults.name} required/></label><label>{t('providers.protocol')}<select name="protocol"><option value="http">http</option><option value="https">https</option></select></label><label>{t('providers.host')}<input name="host" required value={host} onChange={event=>setHost(event.target.value)} placeholder="192.168.1.20"/></label><label>{t('providers.port')}<input key={defaults.port} name="port" inputMode="numeric" defaultValue={defaults.port} placeholder="11434"/></label><label>{t('providers.apiKeyOptional')}<input name="apiKey" type="password" autoComplete="off" placeholder="sk-…"/></label></div>
    <div className="connection-hint"><Server size={14}/><p><strong>{t('providers.sameHostTitle')}</strong> {t('providers.sameHostDescription',{containerHost:'host.containers.internal:11434',localHost:'127.0.0.1:11434'})}</p></div>
    {['127.0.0.1','localhost','::1'].includes(host.trim().toLowerCase()) && <div className="connection-result warning"><XCircle size={17}/><div><strong>{t('providers.loopbackTitle')}</strong><p>{t('providers.loopbackDescription',{containerHost:'host.containers.internal',listenAddress:'0.0.0.0:11434'})}</p></div></div>}
    {result && <div className="connection-result success"><CheckCircle2 size={17}/><div><strong>{t('providers.connectionWorks')}</strong><p>{result.models.length ? t('providers.foundModels',{models:result.models.join(', ')}) : t('providers.noModels')}</p></div></div>}
    {error && <div className="connection-result failed"><XCircle size={17}/><div><strong>{t('providers.connectionFailed')}</strong><p>{error}</p></div></div>}
    <div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>{t('common.actions.cancel')}</button><button type="button" className="button ghost" onClick={onTest} disabled={busy === 'test'}>{busy === 'test' ? <LoaderCircle className="spin" size={15}/> : <Link2 size={15}/>} {t('common.actions.testConnection')}</button><button className="button primary" disabled={busy === 'save'}>{t('common.actions.saveAndSync')}</button></div></form></div>
}
