async () => {
  const checks = [];
  const assert = (condition, message) => { if (!condition) throw new Error(message); checks.push(message); };
  const wait = async predicate => { for (let i=0;i<150;i++) { if (predicate()) return; await new Promise(r=>setTimeout(r,100)); } throw new Error('Timed out'); };
  const id = AppState.datasetId;
  assert(!!id, 'Active dataset exists');
  AppState.columnProfiles=[];
  goToScreen('cleaning');
  await wait(()=>AppState.columnProfiles.length>0);
  assert(document.getElementById('cleaning-content').style.display === 'block', 'Cleaning restores profile state');
  const btn=document.getElementById('btn-preview-cleaning');
  btn.click();
  assert(btn.disabled, 'Preview disabled while processing');
  btn.click();
  await wait(()=>!btn.disabled);
  assert(document.querySelector('.screen.active').id==='screen-quality', 'Preview click opens Data Quality');
  assert(document.getElementById('cleaning-plan').textContent.length>30, 'Recommended actions rendered');
  document.getElementById('btn-apply-cleaning').click();
  await wait(()=>document.querySelector('.screen.active').id==='screen-preview');
  await wait(()=>document.querySelector('#preview-table tbody').children.length>0);
  assert(document.getElementById('audit-log-list').textContent.includes('transformation_summary'), 'Apply opens preview with audit details');
  const workflow=Object.keys(SCREEN_TITLES).filter(s=>s!=='settings');
  goToScreen('upload');
  for(let i=0;i<workflow.length;i++) {
    const section=document.querySelector('.screen.active');
    assert(section.id===`screen-${workflow[i]}`, `Navigation reaches ${workflow[i]}`);
    assert(section.querySelectorAll('.workflow-navigation').length===1,'One workflow footer for '+workflow[i]);
    const buttons=section.querySelectorAll('.workflow-navigation button');
    assert(buttons[0].textContent==='Back' && buttons[1].textContent==='Next','Short labels for '+workflow[i]);
    if(i<workflow.length-1) buttons[1].click();
  }
  assert(AppState.datasetId===id,'Navigation preserves active dataset');
  goToScreen('sql'); await loadSqlMetadata();
  const selector=document.getElementById('sql-table-selector');
  assert(selector && selector.value.includes('"public".'),'Quoted table selector works');
  assert(document.getElementById('sql-columns').textContent.includes('customer_id'),'Column explorer rendered');
  goToScreen('segmentation'); await loadSegmentationScreen();
  assert(document.getElementById('kmeans-cluster-chart').data.length>0,'Cluster distribution rendered');
  assert(document.getElementById('kmeans-scatter-chart').data.length===4,'Four scatter traces rendered');
  assert(document.getElementById('rfm-content').textContent.includes('date'),'Missing transaction date explained');
  const original=apiFetch;
  try {
    apiFetch=async ()=>{throw new Error('Regression test failure');};
    await previewCleaning();
    assert(document.getElementById('cleaning-status').textContent.includes('Regression test failure'),'Preview failure displayed inline');
    assert(!btn.disabled,'Preview re-enabled after failure');
  } finally {apiFetch=original;}
  const exportResponse=await fetch(`/api/dashboard/${id}/export/powerbi`);
  assert(exportResponse.ok && exportResponse.headers.get('content-disposition').includes('.xlsx'),'Power BI export uses XLSX attachment');
  const bytes=new Uint8Array(await exportResponse.arrayBuffer());
  assert(bytes[0]===80 && bytes[1]===75,'Workbook ZIP signature valid');
  return {passed:checks.length, checks};
}
