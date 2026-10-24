function normalizeInvoiceProgress(){
 if(state.activation?.status==='awaiting-verification'&&(!state.businessDetails?.enteredRnc?.trim()||!state.businessDetails?.legalName?.trim())){state.activation={...state.activation,status:'needs-information',step:'details'};return true}return false;
}
function invoiceState(){if(normalizeInvoiceProgress())saved();return state.activation||{path:null,status:'not-started',step:'overview',certificate:null,authorization:null}}
function invoiceStatus(){return tr('invoice_'+invoiceState().status.replaceAll('-','_'))}
function invoiceBadge(){return `<span class="invoice-badge" data-status="${invoiceState().status}">${invoiceStatus()}</span>`}
function invoicePaths(){
 return `<div class="method-options invoice-paths">${[['existing','billing_existing','invoice_existing_desc','M9 12l2 2 4-4'],['new','billing_new','invoice_new_desc','M12 8v8M8 12h8']].map(([path,title,detail,mark])=>`<button type="button" class="method-choice" data-action="invoice-start-${path}"><span class="method-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="${mark}"/></svg></span><span class="method-copy"><strong>${tr(title)}</strong><small>${tr(detail)}</small></span></button>`).join('')}</div><details class="invoice-help"><summary>${tr('invoice_help')}</summary><p>${tr('invoice_help_text')}</p></details>`;
}
function invoiceGuide(){
 if(state.workspace?.country!=='DO')return `<div class="guide-form"><p>${tr('billing_country')}</p></div>`;
 const activation=invoiceState(),readOnly=['active','awaiting-verification'].includes(activation.status);
 if(!activation.path||state.view==='billing-paths')return `<div class="guide-form invoice-guide">${invoicePaths()}</div>`;
 return `<div class="invoice-guide-summary"><div class="formfoot">${button('invoice-open',tr(readOnly?'invoice_view':'invoice_continue'),readOnly?'secondary':'primary')}${!['active','awaiting-verification'].includes(activation.status)?button('invoice-choose-path',tr('invoice_change_path'),'secondary'):''}</div></div>`;
}
function invoiceSummary(){
 const details=state.businessDetails||{},activation=invoiceState();
 return `<dl class="invoice-summary" aria-label="${tr('invoice_summary_title')}"><div><dt>${tr('invoice_path')}</dt><dd>${tr(activation.path==='existing'?'billing_existing':'billing_new')}</dd></div><div><dt>${tr('legal_name')}</dt><dd>${esc(details.legalName)||tr('invoice_missing')}</dd></div><div><dt>RNC</dt><dd>${esc(details.enteredRnc)||tr('invoice_missing')}</dd></div></dl>`;
}
function invoiceDetails(){
 state.taxnumber??=state.businessDetails?.enteredRnc||'';state.legalname??=state.businessDetails?.legalName||'';
 return `<h2 id="invoice-heading" tabindex="-1">${tr('invoice_details')}</h2><p>${tr('invoice_details_intro')}</p><form id="taxform" novalidate><div class="invoice-fields">${field('taxnumber','RNC',state.taxnumber,tr('rnc_example'),'text','off')}${field('legalname',tr('legal_name'),state.legalname,tr('legal_example'),'text','organization')}</div><div id="registryresult"></div><p class="invoice-note">${tr('details_optional')}</p><div class="formfoot"><button class="primary" value="continue">${tr('invoice_save_continue')}</button><button class="secondary" value="close">${tr('invoice_save_close')}</button></div></form><div id="taxstatus" class="feedback" role="status"></div>`;
}
function invoiceQuestion(kind){
 const activation=invoiceState(),options=kind==='certificate'?['invoice_certificate_ready','invoice_certificate_help']:['invoice_authorization_ready','invoice_authorization_help'];
 return `<h2 id="invoice-heading" tabindex="-1">${tr('invoice_'+kind)}</h2><p>${tr('invoice_'+kind+'_intro')}</p><form id="invoice-readiness" data-kind="${kind}" novalidate><fieldset class="invoice-radios" role="radiogroup" aria-required="true" aria-describedby="invoice-answer-error"><legend>${tr('invoice_'+kind+'_question')}</legend>${options.map((label,i)=>`<label><input type="radio" name="readiness" value="${i===0?'ready':'help'}" ${activation[kind]===(i===0?'ready':'help')?'checked':''}><span>${tr(label)}</span></label>`).join('')}</fieldset><div class="feedback-space"><div class="feedback-reserve" aria-hidden="true"><span><i>!</i>${tr('invoice_select_answer')}</span></div><div id="invoice-answer-error" class="feedback error" role="alert"></div></div><div class="formfoot"><button class="primary">${tr('invoice_save_continue')}</button>${button('invoice-close',tr('invoice_save_close'),'secondary')}</div></form>`;
}
function renderInvoiceDossier(){
 clearTimeout(registryTimer);registryVersion++;if(state.registryResult?.status==='checking')state.registryResult=null;
 const activation=invoiceState();$('setuphead').hidden=true;$('setup').classList.add('connection-surface','invoice-surface');$('setupbody').hidden=false;
 let body='';
 if(!activation.path){body=`<h2 id="invoice-heading" tabindex="-1">${tr('invoice_title')}</h2>${button('invoice-choose-path',tr('invoice_change_path'),'primary')}`}
 else if(['active','awaiting-verification'].includes(activation.status)){body=invoiceSummary()}
 else if(activation.status==='needs-information'&&activation.step!=='details'){body=`<h2 id="invoice-heading" tabindex="-1">${tr('invoice_needs_title')}</h2><p>${tr('invoice_needs_body')}</p><div class="formfoot">${button('invoice-details',tr('invoice_edit_details'),'primary')}</div>`}
 else if(activation.step==='details')body=invoiceDetails();
 else if(['certificate','authorization'].includes(activation.step))body=invoiceQuestion(activation.step);
 else if(activation.step==='checks'){body=`<h2 id="invoice-heading" tabindex="-1">${tr(activation.path==='existing'?'invoice_existing_review':'invoice_checks')}</h2><p>${tr(activation.path==='existing'?'invoice_existing_intro':'invoice_checks_intro')}</p>${activation.path==='existing'?`<p class="invoice-note">${tr('invoice_existing_limit')}</p>`:''}${invoiceSummary()}<div class="formfoot">${button('invoice-request-review',tr('invoice_request_review'),'primary')}</div>`}
 else if(activation.path==='existing'){body=`<h2 id="invoice-heading" tabindex="-1">${tr('invoice_existing_review')}</h2><p>${tr('invoice_existing_intro')}</p><p class="invoice-note">${tr('invoice_existing_limit')}</p><div class="formfoot">${button('invoice-details',tr('invoice_review_details'),'primary')}</div>`}
 else body=invoiceDetails();
 const editable=activation.path&&!['awaiting-verification','active'].includes(activation.status);
 $('guidecontent').innerHTML=`<section class="guide-form invoice-dossier"><header class="invoice-context">${destination()}${invoiceBadge()}</header>${editable&&activation.step!=='overview'?button('invoice-back',tr('invoice_back')):''}${body}${editable?`<div class="invoice-path-change">${button('invoice-choose-path',tr('invoice_change_path'))}</div>`:''}<p class="invoice-preview-note">${tr('invoice_preview')}</p></section>`;
 renderInvoicePreviewTools();bindForms();bindInvoice();enhancePickers();
}
function invoiceAction(action){
 let activation={...invoiceState()};
 if(action.startsWith('invoice-start-')){const path=action.slice('invoice-start-'.length);if(activation.path!==path)activation={...activation,path,status:'in-progress',step:'overview'};state.activation=activation;state.view='billing';saved();if(invoiceSurface){render();$('invoice-heading')?.focus({preventScroll:true})}else{render();parent.postMessage({type:'workspace-preview-invoicing'},location.origin)}return}
 if(action==='invoice-choose-path'){state.view='billing-paths';state.collapsed=false;saved();if(invoiceSurface)parent.postMessage({type:'workspace-preview-close-dossier'},location.origin);else render();return}
 if(action==='invoice-open'){parent.postMessage({type:'workspace-preview-invoicing'},location.origin);return}
 if(action==='invoice-close'){saved();parent.postMessage({type:'workspace-preview-close-dossier'},location.origin);return}
 if(action==='invoice-request-review'){activation.status='awaiting-verification';activation.step='overview'}
 else if(action==='invoice-details')activation.step='details';
 else if(action==='invoice-back')activation.step=({details:'overview',certificate:'details',authorization:'certificate',checks:activation.path==='existing'?'details':'authorization'})[activation.step]||'overview';
 state.activation=activation;normalizeInvoiceProgress();saved();render();$('invoice-heading')?.focus({preventScroll:true});
}
function invoiceDetailsSaved(close){
 const activation=invoiceState();state.activation={...activation,status:'in-progress',step:close?'details':activation.path==='existing'?'checks':'certificate'};saved();
 if(close){parent.postMessage({type:'workspace-preview-close-dossier'},location.origin);return}
 render();$('invoice-heading')?.focus({preventScroll:true});
}
function bindInvoice(){
 const form=$('invoice-readiness');if(!form)return;
 form.onchange=()=>{state.activation={...invoiceState(),[form.dataset.kind]:form.querySelector('input:checked')?.value};saved();$('invoice-answer-error').textContent='';form.querySelector('fieldset').removeAttribute('aria-invalid')};
 form.onsubmit=event=>{event.preventDefault();if(!form.querySelector('input:checked')){$('invoice-answer-error').innerHTML='<span class="error-mark" aria-hidden="true">!</span><span>'+tr('invoice_select_answer')+'</span>';form.querySelector('fieldset').setAttribute('aria-invalid','true');form.querySelector('input').focus();return}state.activation={...invoiceState(),step:form.dataset.kind==='certificate'?'authorization':'checks'};saved();render();$('invoice-heading')?.focus({preventScroll:true})};
}
function renderInvoicePreviewTools(){
 $('preview-tools')?.remove();const params=new URLSearchParams(location.search);if(!params.has('review')&&!params.has('qa'))return;
 const states=['not-started','in-progress','needs-information','awaiting-verification','active'];
 const registry=$('taxform')?`<label id="registryfixture-label" for="registryfixture">${tr('lookup_result')}</label><select id="registryfixture">${[['match','lookup_match'],['review','lookup_review'],['no-match','lookup_none'],['unavailable','lookup_unavailable']].map(([value,label])=>`<option value="${value}">${tr(label)}</option>`).join('')}</select>`:'';
 $('setup').insertAdjacentHTML('afterend',`<details id="preview-tools" class="preview-tools"><summary>${tr('preview_controls')}</summary><p>${tr('invoice_preview')}</p><label id="activation-fixture-label" for="activation-fixture">${tr('invoice_state_fixture')}</label><select id="activation-fixture">${states.map(status=>`<option value="${status}">${tr('invoice_'+status.replaceAll('-','_'))}</option>`).join('')}</select>${registry}</details>`);
 $('activation-fixture').value=invoiceState().status;$('activation-fixture').onchange=()=>{const status=$('activation-fixture').value;state.activation={...invoiceState(),path:status==='not-started'?null:invoiceState().path||'new',status,step:'overview'};saved();render();$('preview-tools').open=true;$('activation-fixture-trigger').focus()};
}
