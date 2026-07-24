import { Bot, Box, Code2, Container, Cpu, ExternalLink, Server } from 'lucide-react'
import { useI18n } from '../i18n'

export function DeploymentsPage() {
  const {t}=useI18n()
  return <div className="page"><header className="page-header"><div><p className="eyebrow">{t('deployments.eyebrow')}</p><h1>{t('deployments.title')}</h1><p>{t('deployments.description')}</p></div></header>
    <div className="deployment-grid">
      <article className="deployment-card"><span><Bot/></span><p className="eyebrow">{t('deployments.aiType')}</p><h2>{t('deployments.aiTitle')}</h2><p>{t('deployments.aiText')}</p><ul><li><Cpu size={14}/>{t('deployments.aiPoint1')}</li><li><Box size={14}/>{t('deployments.aiPoint2')}</li><li><Server size={14}/>{t('deployments.aiPoint3')}</li></ul></article>
      <article className="deployment-card"><span><Code2/></span><p className="eyebrow">{t('deployments.scriptType')}</p><h2>{t('deployments.scriptTitle')}</h2><p>{t('deployments.scriptText')}</p><ul><li><Cpu size={14}/>{t('deployments.scriptPoint1')}</li><li><Box size={14}/>{t('deployments.scriptPoint2')}</li><li><Server size={14}/>{t('deployments.scriptPoint3')}</li></ul></article>
      <article className="deployment-card"><span><Container/></span><p className="eyebrow">{t('deployments.customType')}</p><h2>{t('deployments.customTitle')}</h2><p>{t('deployments.customText')}</p><ul><li><ExternalLink size={14}/>{t('deployments.customPoint1')}</li><li><Box size={14}/>{t('deployments.customPoint2')}</li><li><Server size={14}/>{t('deployments.customPoint3')}</li></ul></article>
    </div>
    <section className="panel deployment-flow"><div><strong>{t('deployments.flowDraft')}</strong><small>{t('deployments.flowDraftHint')}</small></div><i>→</i><div><strong>{t('deployments.flowVersion')}</strong><small>{t('deployments.flowVersionHint')}</small></div><i>→</i><div><strong>{t('deployments.flowRuntime')}</strong><small>{t('deployments.flowRuntimeHint')}</small></div><i>→</i><div><strong>{t('deployments.flowTarget')}</strong><small>{t('deployments.flowTargetHint')}</small></div></section>
  </div>
}
