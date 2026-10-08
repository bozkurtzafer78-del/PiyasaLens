import { demoCatalog } from './data-provider.js';

const metrics = {
  THYAO:{market:'BIST',cap:7.8,pe:4.7,yield:1.8,change:2.18,technical:'strong',score:82,growth:21,description:'Türk Hava Yolları · Ulaştırma'},
  ASELS:{market:'BIST',cap:8.4,pe:19.2,yield:.8,change:-.72,technical:'neutral',score:64,growth:17,description:'Aselsan · Savunma'},
  BIMAS:{market:'BIST',cap:9.1,pe:12.8,yield:2.4,change:1.12,technical:'strong',score:78,growth:14,description:'BİM Birleşik Mağazalar · Perakende'},
  GARAN:{market:'BIST',cap:6.3,pe:5.3,yield:3.7,change:-.38,technical:'neutral',score:71,growth:28,description:'Garanti BBVA · Bankacılık'},
  AAPL:{market:'US',cap:3520,pe:34.1,yield:.4,change:1.24,technical:'strong',score:76,growth:11,description:'Apple Inc. · Teknoloji'},
  MSFT:{market:'US',cap:3790,pe:37.8,yield:.7,change:.66,technical:'strong',score:84,growth:16,description:'Microsoft Corp. · Teknoloji'},
  NVDA:{market:'US',cap:4530,pe:48.5,yield:.03,change:2.82,technical:'strong',score:80,growth:72,description:'NVIDIA Corp. · Yarı iletken'},
  SPY:{market:'US',cap:690,pe:25.1,yield:1.2,change:.41,technical:'neutral',score:68,growth:12,description:'SPDR S&P 500 ETF · Endeks ETF'}
};

const state={items:demoCatalog.map(item=>({...item,...metrics[item.symbol]})),results:[],preset:null,selected:null,watchlist:JSON.parse(localStorage.getItem('trader-ai-watchlist')||'[]')};
const $=id=>document.getElementById(id);
const formatPrice=(item)=>`${item.currency==='TRY'?'₺':'$'}${item.price.toLocaleString('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const formatNumber=(value)=>value>=1000?`${(value/1000).toFixed(1)}T`:`${value.toFixed(1)}B`;
const metricLabel=value=>value==='strong'?'Güçlü':value==='weak'?'Zayıf':'Nötr';

function populateSectors(){
  const sectors=[...new Set(state.items.map(item=>item.sector))].sort();
  $('sectorFilter').innerHTML='<option value="ALL">Tüm sektörler</option>'+sectors.map(sector=>`<option value="${sector}">${sector}</option>`).join('');
  $('coverageCount').textContent=state.items.length;
}

function readNumber(id){const value=Number($(id).value);return Number.isFinite(value)&&$(id).value!==''?value:null}

function applyPreset(items){
  if(state.preset==='value')return items.filter(item=>item.pe<=15).sort((a,b)=>a.pe-b.pe);
  if(state.preset==='dividend')return items.filter(item=>item.yield>=1.5).sort((a,b)=>b.yield-a.yield);
  if(state.preset==='momentum')return items.filter(item=>item.technical==='strong').sort((a,b)=>b.change-a.change);
  if(state.preset==='quality')return items.filter(item=>item.score>=75).sort((a,b)=>b.score-a.score);
  return items;
}

function filterItems(){
  const market=$('marketFilter').value,sector=$('sectorFilter').value,technical=$('technicalFilter').value;
  const minPrice=readNumber('minPrice'),maxPrice=readNumber('maxPrice'),minCap=readNumber('minCap'),maxCap=readNumber('maxCap'),minPe=readNumber('minPe'),maxPe=readNumber('maxPe'),minYield=readNumber('minYield'),maxYield=readNumber('maxYield');
  let items=state.items.filter(item=>(market==='ALL'||item.market===market)&&(sector==='ALL'||item.sector===sector)&&(technical==='ALL'||item.technical===technical)&&(minPrice===null||item.price>=minPrice)&&(maxPrice===null||item.price<=maxPrice)&&(minCap===null||item.cap>=minCap)&&(maxCap===null||item.cap<=maxCap)&&(minPe===null||item.pe>=minPe)&&(maxPe===null||item.pe<=maxPe)&&(minYield===null||item.yield>=minYield)&&(maxYield===null||item.yield<=maxYield));
  state.results=applyPreset(items);
  const sort=$('sortResults').value;
  state.results.sort((a,b)=>sort==='change'?b.change-a.change:sort==='pe'?a.pe-b.pe:sort==='yield'?b.yield-a.yield:b.score-a.score);
  renderResults();
}

function renderResults(){
  const body=$('resultsBody');
  $('resultSummary').textContent=`${state.results.length} hisse eşleşti`;
  $('emptyResults').hidden=state.results.length>0;
  body.innerHTML=state.results.map(item=>{const watched=state.watchlist.includes(item.symbol);return `<tr data-symbol="${item.symbol}" class="${state.selected===item.symbol?'selected':''}"><td><div class="company-cell"><span class="company-icon">${item.symbol.slice(0,2)}</span><span><strong>${item.symbol}</strong><small>${item.name}</small></span></div></td><td>${formatPrice(item)}</td><td class="${item.change>=0?'gain':'loss'}">${item.change>=0?'+':''}${item.change.toFixed(2)}%</td><td>${formatNumber(item.cap)}</td><td>${item.pe.toFixed(1)}</td><td>${item.yield.toFixed(2)}%</td><td class="technical ${item.technical}">${metricLabel(item.technical)}</td><td><span class="score">${item.score}%</span></td><td><button class="row-actions" data-watch="${item.symbol}" aria-label="${item.symbol} takip listesine ${watched?'çıkar':'ekle'}">${watched?'★':'☆'}</button></td></tr>`}).join('');
  body.querySelectorAll('tr[data-symbol]').forEach(row=>row.addEventListener('click',event=>{if(event.target.closest('[data-watch]'))return;selectItem(row.dataset.symbol)}));
  body.querySelectorAll('[data-watch]').forEach(button=>button.addEventListener('click',event=>{event.stopPropagation();toggleWatchlist(button.dataset.watch)}));
}

function selectItem(symbol){
  state.selected=symbol;const item=state.items.find(x=>x.symbol===symbol);if(!item)return;
  $('selectionSummary').innerHTML=`<div><div class="summary-stock"><span class="company-icon">${item.symbol.slice(0,2)}</span><div><h3>${item.symbol} · ${formatPrice(item)}</h3><p>${item.description} · AI eşleşmesi <strong>${item.score}%</strong></p></div></div><ul class="reason-list"><li>${item.score>=75?'Güçlü':'Orta'} kalite ve kriter uyumu</li><li>${item.pe<15?'Değerleme çarpanı makul':'Büyüme beklentisi değerlemeyi destekliyor'}</li><li>Teknik görünüm: ${metricLabel(item.technical)} · Günlük değişim ${item.change>=0?'+':''}${item.change.toFixed(2)}%</li></ul></div>`;
  renderResults();
}

function toggleWatchlist(symbol){state.watchlist=state.watchlist.includes(symbol)?state.watchlist.filter(x=>x!==symbol):[...state.watchlist,symbol];localStorage.setItem('trader-ai-watchlist',JSON.stringify(state.watchlist));renderResults();renderWatchlist()}
function renderWatchlist(){const el=$('watchlistItems');el.innerHTML=state.watchlist.length?state.watchlist.map(symbol=>{const item=state.items.find(x=>x.symbol===symbol);return `<div class="watch-line"><b>${symbol}</b><span>${item?formatPrice(item):'—'} <button class="text-button" data-remove-watch="${symbol}">Kaldır</button></span></div>`}).join(''):'<p class="muted">Henüz hisse eklenmedi.</p>';el.querySelectorAll('[data-remove-watch]').forEach(button=>button.onclick=()=>toggleWatchlist(button.dataset.removeWatch))}

function runPrompt(){
  const prompt=$('aiPrompt').value.toLowerCase();
  state.preset=prompt.includes('temett')?'dividend':prompt.includes('momentum')||prompt.includes('rsi')?'momentum':prompt.includes('ucuz')||prompt.includes('değer')?'value':prompt.includes('kalite')||prompt.includes('borcu düşük')?'quality':null;
  const labels=state.preset==='dividend'?'Temettü · Düşük risk':state.preset==='momentum'?'Teknik güç · Momentum':state.preset==='value'?'Değerleme · Ucuzluk':state.preset==='quality'?'Kalite · Bilanço':'Büyüme · Değerleme · Teknik güç';
  $('promptInterpretation').innerHTML=`<span>Yorumlanan kriterler</span><b> ${labels}</b>`;filterItems();
}

document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{$('aiPrompt').value=button.dataset.prompt;runPrompt()});
$('runPrompt').onclick=runPrompt;$('aiPrompt').addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key==='Enter')runPrompt()});
$('applyFilters').onclick=()=>{state.preset=null;filterItems()};$('sortResults').onchange=filterItems;
$('clearFilters').onclick=()=>{['marketFilter','sectorFilter','technicalFilter'].forEach(id=>$(id).value='ALL');['minPrice','maxPrice','minCap','maxCap','minPe','maxPe','minYield','maxYield'].forEach(id=>$(id).value='');state.preset=null;filterItems()};
document.querySelectorAll('[data-category]').forEach(button=>button.onclick=()=>{document.querySelectorAll('[data-category]').forEach(item=>item.classList.remove('active'));button.classList.add('active');$('promptInterpretation').innerHTML=`<span>Aktif kategori</span><b> ${button.textContent}</b>`});
$('saveScreen').onclick=()=>{localStorage.setItem('trader-ai-screen',JSON.stringify({prompt:$('aiPrompt').value,updatedAt:new Date().toISOString()}));$('saveScreen').textContent='Ekran kaydedildi';setTimeout(()=>$('saveScreen').textContent='Ekranı kaydet',1400)};
$('clearWatchlist').onclick=()=>{state.watchlist=[];localStorage.removeItem('trader-ai-watchlist');renderResults();renderWatchlist()};

async function loadProviderStatus(){try{const response=await fetch('http://127.0.0.1:4180/api/status');if(!response.ok)throw new Error('status');const status=await response.json();$('providerPill').innerHTML=`<i></i> ${status.mode==='configured'?status.provider:'Demo veri'}`;$('updatedAt').textContent=new Date(status.lastSuccessfulUpdate).toLocaleString('tr-TR')}catch{$('updatedAt').textContent='yerel demo'}}

populateSectors();renderWatchlist();filterItems();selectItem('THYAO');loadProviderStatus();
