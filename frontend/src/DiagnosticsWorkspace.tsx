import { useState } from 'react';
import DataOperations from './DataOperations';
import OriginalUploader from './OriginalUploader';

/** Explicit developer view: no heavy diagnostic reads until requested. */
export default function DiagnosticsWorkspace(){
  const [open,setOpen]=useState(false);
  const [content,setContent]=useState('');
  const [busy,setBusy]=useState(false);

  async function showConsole(){
    if(open){setOpen(false);return;}
    setOpen(true);setBusy(true);setContent('');
    try{
      const response=await fetch('/api/data/debug-console',{cache:'no-store'});
      if(!response.ok)throw new Error('Diagnostic console unavailable (HTTP '+response.status+')');
      setContent(JSON.stringify(await response.json(),null,2));
    }catch(cause){
      setContent(cause instanceof Error?cause.message:'Diagnostic console unavailable');
    }finally{setBusy(false);}
  }

  return <section id="diagnostics" className="research-source-shell workspace-diagnostics" tabIndex={-1}>
    <h2>Diagnostics &amp; administration</h2>
    <p>Historical maintenance, original archive administration and investigation tools.</p>
    <button type="button" onClick={()=>void showConsole()} aria-expanded={open}>
      {open?'Close diagnostic console':'Open diagnostic console'}
    </button>
    {open&&<pre tabIndex={0} aria-label="Full diagnostic console"
      style={{maxHeight:'65vh',overflow:'auto',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>
      {busy?'Loading diagnostics…':content}
    </pre>}
    <DataOperations/>
    <OriginalUploader/>
  </section>;
}
