import { api } from './api'

export type ToastLevel='success'|'info'|'warning'|'error'
export type ToastNotice={id:string;message:string;level:ToastLevel}
type Audit={kind?:string;resource_type?:string;resource_id?:string;payload?:Record<string,unknown>}

export function toast(message:string,level:ToastLevel='info',audit?:Audit){
  const notice:ToastNotice={id:crypto.randomUUID(),message,level}
  window.dispatchEvent(new CustomEvent<ToastNotice>('agent-forge:toast',{detail:notice}))
  if(audit)void api('/audit-events',{method:'POST',body:JSON.stringify({kind:audit.kind??'ui.toast',level,message,resource_type:audit.resource_type??null,resource_id:audit.resource_id??null,payload:audit.payload??{}})}).catch(()=>undefined)
}
