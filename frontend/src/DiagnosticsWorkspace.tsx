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

  return <div className="data-tools-body">
    <section className="data-technical-console" aria-label="Technical console">
      <h4>Detailed errors and system events</h4>
      <p>Shows the technical details behind failed downloads, file imports, and research checks.</p>
      <button type="button" onClick={()=>void showConsole()} aria-expanded={open}
        aria-controls="data-technical-log">
        {open?'Hide error and event details':'Show error and event details'}
      </button>
      {open&&<pre id="data-technical-log" tabIndex={0} aria-label="Full diagnostic console"
        style={{maxHeight:360,overflow:'auto',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>
        {busy?'Loading diagnostics…':content}
      </pre>}
    </section>
    <section className="data-technical-maintenance" aria-label="Additional maintenance">
      <h4>Additional checks</h4>
      <DataOperations/>
    </section>
    <OriginalUploader/>
  </div>;
}
