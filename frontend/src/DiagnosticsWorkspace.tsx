import { useState } from 'react';

/** Technical evidence is read only after a person requests it. */
export default function DiagnosticsWorkspace(){
  const [open,setOpen]=useState(false);
  const [content,setContent]=useState('');
  const [busy,setBusy]=useState(false);

  async function showConsole(){
    if(open){setOpen(false);return;}
    setOpen(true);setBusy(true);setContent('');
    try{
      const response=await fetch('/api/data/debug-console',{cache:'no-store'});
      if(!response.ok)throw new Error('Technical event log unavailable (HTTP '+response.status+')');
      setContent(JSON.stringify(await response.json(),null,2));
    }catch(cause){
      setContent(cause instanceof Error?cause.message:'Technical event log unavailable');
    }finally{setBusy(false);}
  }

  return <div className="data-tools-body">
    <section className="data-technical-console" aria-label="Technical event log">
      <h4>Technical event log</h4>
      <p>Inspect the recorded errors and application events if you need to identify
        exactly where a data check failed. The ZIP above contains the fuller evidence.</p>
      <button type="button" onClick={()=>void showConsole()} aria-expanded={open}
        aria-controls="data-technical-log">
        {open?'Close event log':'View technical event log'}
      </button>
      {open&&<pre id="data-technical-log" tabIndex={0} aria-label="Full diagnostic console"
        style={{maxHeight:360,overflow:'auto',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>
        {busy?'Loading events…':content}
      </pre>}
    </section>
  </div>;
}
