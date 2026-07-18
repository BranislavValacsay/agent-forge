import { useEffect, useState } from 'react'
import { CheckCircle2, Info, TriangleAlert, XCircle } from 'lucide-react'
import type { ToastNotice } from '../lib/toast'

export function ToastViewport(){
  const [items,setItems]=useState<ToastNotice[]>([])
  useEffect(()=>{
    const listener=(event:Event)=>{
      const notice=(event as CustomEvent<ToastNotice>).detail
      setItems(current=>[...current.slice(-3),notice])
      window.setTimeout(()=>setItems(current=>current.filter(item=>item.id!==notice.id)),4200)
    }
    window.addEventListener('agent-forge:toast',listener)
    return()=>window.removeEventListener('agent-forge:toast',listener)
  },[])
  return <aside className="toast-viewport" aria-live="polite">{items.map(item=><div className={`toast ${item.level}`} key={item.id}>{item.level==='success'?<CheckCircle2/>:item.level==='error'?<XCircle/>:item.level==='warning'?<TriangleAlert/>:<Info/>}<span>{item.message}</span><i/></div>)}</aside>
}
