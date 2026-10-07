const state = { market: 'BIST', filter: 'all', query: '', sortKey: 'screen_score', sortDir: -1, data: null, strategy: null, selected: null, alerts: JSON.parse(localStorage.getItem('trader-alerts') || '{}'), watchlist: new Set(JSON.parse(localStorage.getItem('trader-watchlist') || '[]')) };
const $ = (id) => document.getElementById(id);
let cloud = null;
let cloudUser = null;
const localizeAiText = (value) => String(value || '').replace(/relative_volume/gi, 'göreli hacim').replace(/market cap/gi, 'piyasa değeri').replace(/ROE/gi, 'özsermaye kârlılığı').replace(/EBITDA/gi, 'FAVÖK').replace(/buy/gi, 'alım').replace(/hold/gi, 'izle').replace(/avoid/gi, 'kaçın');
const localizeDecision = (value) => ({ BUY: 'ALIM', HOLD: 'İZLE', AVOID: 'KAÇIN', BUY_MORE: 'ALIM', SELL: 'KAÇIN' }[String(value || '').toUpperCase()] || value || 'İZLE');
const number = (value, digits = 2) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString('tr-TR', { maximumFractionDigits: digits });
const pct = (value) => value == null ? '—' : `${Number(value) > 0 ? '+' : ''}${number(value)}%`;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
function alertText(item, alert) {
  if (!alert || (!alert.price && !alert.returnPct)) return 'Bu sembol için alarm kurulmadı.';
  const reached = alert.price && Number(item.price) >= Number(alert.price);
  return reached ? `Alarm tetiklendi · mevcut fiyat ${number(item.price)} hedefin üzerinde.` : `Alarm aktif · hedef ${alert.price ? number(alert.price) : '—'} · minimum getiri ${number(alert.returnPct ?? 5, 1)}%.`;
}
function targetReached(item, alert) {
  return Boolean((alert?.price && Number(item.price) >= Number(alert.price)) || (alert?.returnPct && Number(item.change_pct) >= Number(alert.returnPct)));
}
function updateNotificationStatus() {
  const status = $('notificationStatus');
  if (!('Notification' in window)) { status.textContent = 'Tarayıcı bildirimleri desteklemiyor'; return; }
  status.textContent = Notification.permission === 'granted' ? 'Bildirimler etkin' : Notification.permission === 'denied' ? 'Bildirimler engellendi' : 'Etkin değil';
}
function notifyIfTriggered(item, alert) {
  if (!targetReached(item, alert) || !('Notification' in window) || Notification.permission !== 'granted') return;
  const key = `${item.symbol}:${alert.updatedAt || alert.price}`;
  if (localStorage.getItem('trader-alert-notified') === key) return;
  const target = alert.price ? `fiyat hedefi ${number(alert.price)}` : `minimum getiri ${number(alert.returnPct, 1)}%`;
  new Notification(`${item.symbol} alarmı tetiklendi`, { body: `Mevcut fiyat ${number(item.price)} · ${target}` });
  localStorage.setItem('trader-alert-notified', key);
}

function currentItems() {
  return state.data?.markets?.[state.market]?.items || [];
}
function renderWatchlist() {
  const items = [...state.watchlist];
  $('watchlistItems').innerHTML = items.length ? items.map((symbol) => `<div class="watchlist-item"><button class="watch-symbol" data-open-watch="${esc(symbol)}">${esc(symbol)}</button><button class="remove-watch" data-remove-watch="${esc(symbol)}" aria-label="${esc(symbol)} takipten çıkar">×</button></div>`).join('') : '<span class="muted">Listen boş.</span>';
  document.querySelectorAll('[data-open-watch]').forEach((button) => button.addEventListener('click', () => { openSymbol(button.dataset.openWatch); $('watchlistMenu').hidden = true; $('watchlistButton').setAttribute('aria-expanded', 'false'); }));
  document.querySelectorAll('[data-remove-watch]').forEach((button) => button.addEventListener('click', () => { state.watchlist.delete(button.dataset.removeWatch); persistLocalState(); persistCloudState(); renderWatchlist(); $('watchlistButton').textContent = state.watchlist.size ? `☆ ${state.watchlist.size}` : '☆'; if (state.selected?.symbol === button.dataset.removeWatch) $('watchlistToggle').textContent = '☆ Takip listesine ekle'; }));
}

function persistLocalState() {
  localStorage.setItem('trader-watchlist', JSON.stringify([...state.watchlist]));
  localStorage.setItem('trader-alerts', JSON.stringify(state.alerts));
}

async function persistCloudState() {
  if (!cloudUser || !cloud) return;
  try { await cloud.setDoc(cloud.profileRef(cloudUser.uid), { watchlist: [...state.watchlist], alerts: state.alerts, updatedAt: new Date().toISOString() }, { merge: true }); }
  catch { $('accountStatus').textContent = 'Bulut kaydı şu an kullanılamıyor; cihazdaki kayıt korunuyor.'; }
}

function updateAccountUi() {
  const button = $('accountButton');
  if (!button) return;
  button.textContent = cloudUser ? (cloudUser.email?.slice(0, 1).toUpperCase() || '✓') : 'Z';
  $('accountCopy').textContent = cloudUser ? `${cloudUser.email} hesabı ile senkronize ediliyor.` : 'Takip listesi, portföy ve alarm ayarlarını hesabınıza kaydedin.';
  $('accountForm').hidden = Boolean(cloudUser);
  $('signOutButton').hidden = !cloudUser;
}

async function initCloudAccount() {
  try { cloud = await import('./firebase-client.js'); }
  catch { return; }
  cloud.onAuthStateChanged(cloud.auth, async (user) => {
    cloudUser = user;
    updateAccountUi();
    if (!user) return;
    try {
      const snapshot = await cloud.getDoc(cloud.profileRef(user.uid));
      if (snapshot.exists()) {
        const profile = snapshot.data();
        state.watchlist = new Set(Array.isArray(profile.watchlist) ? profile.watchlist : []);
        state.alerts = profile.alerts && typeof profile.alerts === 'object' ? profile.alerts : {};
        persistLocalState();
        renderWatchlist();
        if (state.selected) selectSymbol(state.selected.symbol);
      } else await persistCloudState();
    } catch { $('accountStatus').textContent = 'Bulut veritabanı henüz etkin değil; cihazdaki kayıt korunuyor.'; }
  });
}

async function loadSources(item) {
  const encodedSymbol = encodeURIComponent(item.symbol);
  if (item.market !== 'BIST') {
    $('sourceLinks').innerHTML = '<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">ABD</span></div><p class="muted source-loading">SEC bildirimleri aranıyor…</p>';
    try {
      const response = await fetch(`/api/sec?symbol=${encodedSymbol}`);
      const payload = await response.json();
      const items = payload.items || [];
      $('sourceLinks').innerHTML = `<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">${items.length} bildirim</span></div>${items.length ? items.map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer"><span>${esc(source.form)} · ${esc(source.title)}<small>${esc(source.date)}</small></span><b>↗</b></a>`).join('') : `<p class="muted source-loading">SEC eşleşmesi bulunamadı. <a href="https://www.sec.gov/edgar/search/#/q=${encodedSymbol}" target="_blank" rel="noreferrer">EDGAR aramasını aç ↗</a></p>`}`;
    } catch {
      $('sourceLinks').innerHTML = `<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">ABD</span></div><a href="https://www.sec.gov/edgar/search/#/q=${encodedSymbol}" target="_blank" rel="noreferrer">SEC EDGAR aramasını aç <span>↗</span></a>`;
    }
    return;
  }
  $('sourceLinks').innerHTML = '<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">BIST</span></div><p class="muted source-loading">KAP bildirimleri aranıyor…</p>';
  try {
    const response = await fetch(`/api/kap?symbol=${encodedSymbol}`);
    const payload = await response.json();
    const items = payload.items || [];
    $('sourceLinks').innerHTML = `<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">${items.length} bildirim</span></div>${items.length ? items.map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer"><span>${esc(source.title)}<small>${esc(source.date)}</small></span><b>↗</b></a>`).join('') : '<p class="muted source-loading">Son 48 saatte eşleşen KAP bildirimi bulunamadı.</p>'}`;
  } catch {
    $('sourceLinks').innerHTML = `<div class="source-head"><span class="panel-kicker">BİRİNCİL KAYNAKLAR</span><span class="muted">BIST</span></div><a href="https://www.kap.org.tr/tr/" target="_blank" rel="noreferrer">KAP portalını aç <span>↗</span></a>`;
  }
}

function signal(item) {
  if ((item.screen_score || 0) >= 80) return ['review', 'İncele'];
  if ((item.screen_score || 0) < 50) return ['risk', 'Risk'];
  return ['watch', 'İzle'];
}

function renderTable() {
  const query = state.query.toLocaleUpperCase('tr-TR');
  let items = currentItems().filter((item) => `${item.symbol} ${item.name}`.toLocaleUpperCase('tr-TR').includes(query));
  if (state.filter === 'score') items = items.filter((item) => (item.screen_score || 0) >= 80);
  if (state.filter === 'gainers') items = items.filter((item) => (item.change_pct || 0) > 0);
  if (state.filter === 'liquid') {
    const minimumVolume = state.market === 'BIST' ? 100000 : 500000;
    items = items.filter((item) => (item.volume || 0) >= minimumVolume);
  }
  if (state.filter === 'ai') items = items.filter((item) => (state.strategy?.result?.picks || []).some((pick) => pick.symbol === item.symbol));
  items = [...items].sort((a, b) => {
    const left = a[state.sortKey];
    const right = b[state.sortKey];
    if (typeof left === 'string' || typeof right === 'string') return String(left ?? '').localeCompare(String(right ?? ''), 'tr-TR') * state.sortDir;
    return ((Number(left) || 0) - (Number(right) || 0)) * state.sortDir;
  }).slice(0, 40);
  $('tableCount').textContent = `${items.length} sonuç gösteriliyor`;
  const sortNames = { symbol: 'sembol', price: 'fiyat', change_pct: 'değişim', screen_score: 'skor', rsi_14: 'RSI', pe: 'F/K', relative_volume: 'göreli hacim' };
  $('sortLabel').textContent = `${sortNames[state.sortKey] || state.sortKey} · ${state.sortDir === -1 ? 'azalan' : 'artan'} sıralama`;
  $('screenerBody').innerHTML = items.length ? items.map((item, index) => {
    const [kind, label] = signal(item);
    const active = state.selected?.symbol === item.symbol ? ' selected' : '';
    return `<tr class="${active}" data-symbol="${esc(item.symbol)}"><td class="rank">${String(index + 1).padStart(2, '0')}</td><td><div class="symbol-cell"><span class="symbol-icon">${esc(item.symbol.slice(0, 2))}</span><span><b>${esc(item.symbol)}</b><small>${esc(item.name)}</small></span></div></td><td>${number(item.price)}</td><td class="${(item.change_pct || 0) >= 0 ? 'positive' : 'negative'}">${pct(item.change_pct)}</td><td class="score">${number(item.screen_score, 0)}</td><td>${number(item.rsi_14, 1)}</td><td>${number(item.pe, 1)}</td><td>${number(item.relative_volume, 2)}x</td><td><span class="signal ${kind}">${label}</span></td></tr>`;
  }).join('') : '<tr><td colspan="9" class="empty">Bu filtreyle eşleşen sembol yok.</td></tr>';
  document.querySelectorAll('[data-symbol]').forEach((row) => row.addEventListener('click', () => selectSymbol(row.dataset.symbol)));
}

function selectSymbol(symbol) {
  state.selected = currentItems().find((item) => item.symbol === symbol) || null;
  if (!state.selected) return;
  const item = state.selected;
  $('detailTitle').textContent = `${item.symbol} · ${item.name}`;
  $('detailCopy').textContent = `Tarama skoru ${number(item.screen_score, 0)}/100. ${item.screen_reasons?.length ? `Öne çıkan sinyaller: ${item.screen_reasons.join(', ')}.` : 'Bu sembol için açıklanabilir sinyal bulunamadı.'}`;
  $('detailMetrics').innerHTML = [['Fiyat', number(item.price)], ['Değişim', pct(item.change_pct)], ['F/K', number(item.pe, 1)], ['Özsermaye kârlılığı', pct(item.roe)], ['Borç / özsermaye', number(item.debt_to_equity, 2)], ['RSI', number(item.rsi_14, 1)], ['Göreli hacim', `${number(item.relative_volume, 2)}x`]].map(([label, value]) => `<span><b>${esc(label)}</b> ${esc(value)}</span>`).join('');
  const alert = state.alerts[item.symbol] || {};
  $('alertPrice').value = alert.price ?? '';
  $('alertReturn').value = alert.returnPct ?? 5;
  $('alertStatus').textContent = alertText(item, alert);
  $('alertStatus').classList.toggle('active', Boolean(alert.price || alert.returnPct));
  $('alertStatus').classList.toggle('triggered', targetReached(item, alert));
  updateNotificationStatus();
  notifyIfTriggered(item, alert);
  const aiPick = (state.strategy?.result?.picks || []).find((pick) => pick.symbol === item.symbol);
  $('aiEvidence').innerHTML = aiPick ? `<div class="evidence-head"><span class="panel-kicker purple">ANALİZ KANITI</span><span class="decision-pill ${aiPick.decision}">${esc(localizeDecision(aiPick.decision))} · ${number(aiPick.confidence, 0)}%</span></div><p>${esc(localizeAiText(aiPick.thesis))}</p><div class="evidence-columns"><div><b>Riskler</b><ul>${(aiPick.risks || []).map((risk) => `<li>${esc(localizeAiText(risk))}</li>`).join('')}</ul></div><div><b>Katalizörler</b><ul>${(aiPick.catalysts || []).map((catalyst) => `<li>${esc(localizeAiText(catalyst))}</li>`).join('')}</ul></div></div>` : '<div class="evidence-head"><span class="panel-kicker purple">ANALİZ KANITI</span><span class="muted">Bu sembol yapay zekâ listesinin dışında</span></div><p class="muted">Bu sembol için yapay zekâ açıklaması henüz bulunmuyor.</p>';
  loadSources(item);
  $('watchlistToggle').disabled = false;
  $('saveAlert').disabled = false;
  $('watchlistToggle').textContent = state.watchlist.has(item.symbol) ? '★ Takipte' : '☆ Takip listesine ekle';
  renderTable();
}

function openSymbol(symbol) {
  const market = Object.keys(state.data?.markets || {}).find((key) => (state.data.markets[key].items || []).some((item) => item.symbol === symbol));
  if (market && market !== state.market) switchMarket(market);
  selectSymbol(symbol);
  document.getElementById('method').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function renderPicks() {
  const result = state.strategy?.result;
  $('aiSummary').textContent = localizeAiText(result?.market_summary || 'Yapay zekâ analizi henüz oluşturulmadı.');
  const picks = result?.picks || [];
  $('aiPicks').innerHTML = picks.length ? picks.map((pick) => `<article class="ai-pick" data-ai-symbol="${esc(pick.symbol)}"><span class="ai-rank">#${pick.rank}</span><div><b>${esc(pick.symbol)}</b><p>${esc(localizeAiText(pick.thesis))}</p></div><span class="confidence">${number(pick.confidence, 0)}%</span></article>`).join('') : '<p class="empty">Henüz yapay zekâ seçimi yok.</p>';
  document.querySelectorAll('[data-ai-symbol]').forEach((card) => card.addEventListener('click', () => openSymbol(card.dataset.aiSymbol)));
}

function renderStats() {
  const bist = state.data?.markets?.BIST?.items || [];
  const us = state.data?.markets?.US?.items || [];
  const items = [...bist, ...us];
  const leader = [...items].sort((a, b) => (b.screen_score || 0) - (a.screen_score || 0))[0];
  $('statUniverse').textContent = number(items.length, 0);
  $('statScore').textContent = leader ? number(leader.screen_score, 0) : '—';
  $('statLeader').textContent = leader ? `${leader.symbol} · ${leader.market}` : '—';
  $('statPositive').textContent = number(items.filter((item) => (item.screen_score || 0) >= 70).length, 0);
  const date = state.data?.generated_at ? new Date(state.data.generated_at) : null;
  $('statFreshness').textContent = date ? date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '—';
  $('refreshDate').textContent = date ? date.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
}

function switchMarket(market) {
  state.market = market;
  document.querySelectorAll('[data-market]').forEach((button) => button.classList.toggle('active', button.dataset.market === market));
  const aiFilter = document.querySelector('[data-filter="ai"]');
  if (aiFilter) aiFilter.textContent = 'Yapay zekâ seçimleri';
  const aiMethodTag = document.querySelector('.method-tags span:last-child');
  if (aiMethodTag) aiMethodTag.textContent = 'Yapay zekâ özeti';
  const count = state.data?.markets?.[market]?.row_count || currentItems().length;
  $('universeLabel').textContent = `${market === 'US' ? 'ABD' : market} evreni · ${number(count, 0)} sembol`;
  state.selected = null;
  $('detailTitle').textContent = 'Bir sembol seç';
  $('detailCopy').textContent = 'Skor bileşenlerini ve temel metrikleri görmek için bir satıra tıkla.';
  $('detailMetrics').innerHTML = '';
  $('saveAlert').disabled = true;
  $('alertPrice').value = '';
  $('alertReturn').value = 5;
  $('alertStatus').textContent = 'Alarm kurmak için bir sembol seç.';
  $('aiEvidence').innerHTML = '';
  $('sourceLinks').innerHTML = '';
  $('watchlistToggle').disabled = true;
  renderTable();
}

async function loadData() {
  try {
    const [marketResponse, staticResponse, strategyResponse] = await Promise.all([
      fetch('/api/market?ts=' + Date.now()).catch(() => null),
      fetch('/data/latest_market.json?ts=' + Date.now()),
      fetch('/data/latest_strategy.json?ts=' + Date.now())
    ]);
    if (!staticResponse.ok && !marketResponse?.ok) throw new Error('market data unavailable');
    const remote = marketResponse?.ok ? await marketResponse.json() : null;
    const fallback = staticResponse.ok ? await staticResponse.json() : null;
    state.data = remote?.markets ? remote : fallback;
    if (!state.data) throw new Error('market data unavailable');
    state.strategy = strategyResponse.ok ? await strategyResponse.json() : null;
    const generatedAt = state.data.generated_at ? new Date(state.data.generated_at) : null;
    const ageHours = generatedAt && !Number.isNaN(generatedAt.getTime()) ? (Date.now() - generatedAt.getTime()) / 3600000 : Infinity;
    const ok = !state.data.errors?.length && Object.keys(state.data.markets || {}).length;
    const statusLabel = !ok ? 'veri uyarısı' : ageHours > 36 ? 'veri eski' : 'günlük doğrulanmış veri';
    $('dataStatus').innerHTML = `<i></i> ${statusLabel}`;
    $('dataStatus').title = ok && ageHours > 36 ? 'Son tarama 36 saatten daha eski.' : 'Son tamamlanan günlük tarama.';
    renderStats(); renderPicks(); switchMarket(state.market);
    [...state.watchlist].forEach((symbol) => {
      const item = [...(state.data.markets.BIST?.items || []), ...(state.data.markets.US?.items || [])].find((candidate) => candidate.symbol === symbol);
      if (item) notifyIfTriggered(item, state.alerts[symbol]);
    });
  } catch (error) {
    $('dataStatus').innerHTML = '<i></i> veri kullanılamıyor';
    $('screenerBody').innerHTML = '<tr><td colspan="9" class="empty">Piyasa verisi yüklenemedi. Önce veri taramasını çalıştır.</td></tr>';
  }
}

document.querySelectorAll('[data-market]').forEach((button) => button.addEventListener('click', () => switchMarket(button.dataset.market)));
document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => { state.filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach((item) => item.classList.toggle('active', item === button)); renderTable(); }));
document.querySelectorAll('[data-sort]').forEach((header) => header.addEventListener('click', () => { const key = header.dataset.sort; if (state.sortKey === key) state.sortDir *= -1; else { state.sortKey = key; state.sortDir = key === 'symbol' ? 1 : -1; } document.querySelectorAll('[data-sort]').forEach((item) => item.classList.toggle('sorted', item === header)); renderTable(); }));
$('search').addEventListener('input', (event) => { state.query = event.target.value; renderTable(); });
$('clearSearch').addEventListener('click', () => { $('search').value = ''; state.query = ''; renderTable(); $('search').focus(); });
$('watchlistToggle').addEventListener('click', () => {
  if (!state.selected) return;
  if (state.watchlist.has(state.selected.symbol)) state.watchlist.delete(state.selected.symbol);
  else state.watchlist.add(state.selected.symbol);
  persistLocalState();
  persistCloudState();
  $('watchlistToggle').textContent = state.watchlist.has(state.selected.symbol) ? '★ Takipte' : '☆ Takip listesine ekle';
  $('watchlistButton').textContent = state.watchlist.size ? `☆ ${state.watchlist.size}` : '☆';
  renderWatchlist();
});
$('saveAlert').addEventListener('click', () => {
  if (!state.selected) return;
  const price = Number($('alertPrice').value) || null;
  const returnPct = Number($('alertReturn').value) || 5;
  if (!price && !returnPct) { delete state.alerts[state.selected.symbol]; $('alertStatus').textContent = 'Alarm kaldırıldı.'; $('alertStatus').classList.remove('active'); }
  else { state.alerts[state.selected.symbol] = { price, returnPct, updatedAt: new Date().toISOString() }; $('alertStatus').textContent = alertText(state.selected, state.alerts[state.selected.symbol]); $('alertStatus').classList.add('active'); $('alertStatus').classList.toggle('triggered', targetReached(state.selected, state.alerts[state.selected.symbol])); notifyIfTriggered(state.selected, state.alerts[state.selected.symbol]); }
  persistLocalState();
  persistCloudState();
});
$('enableNotifications').addEventListener('click', async () => { if (!('Notification' in window)) return updateNotificationStatus(); await Notification.requestPermission(); updateNotificationStatus(); if (state.selected) notifyIfTriggered(state.selected, state.alerts[state.selected.symbol]); });
updateNotificationStatus();
$('watchlistButton').addEventListener('click', () => { const menu = $('watchlistMenu'); menu.hidden = !menu.hidden; $('watchlistButton').setAttribute('aria-expanded', String(!menu.hidden)); });
$('accountButton').addEventListener('click', () => { $('accountDialog').hidden = false; $('accountEmail').focus(); });
$('closeAccount').addEventListener('click', () => { $('accountDialog').hidden = true; });
$('accountDialog').addEventListener('click', (event) => { if (event.target === $('accountDialog')) $('accountDialog').hidden = true; });
$('accountForm').addEventListener('submit', async (event) => { event.preventDefault(); if (!cloud) { $('accountStatus').textContent = 'Hesap bağlantısı yüklenemedi; yerel kayıt kullanılabilir.'; return; } $('accountStatus').textContent = 'Giriş yapılıyor…'; try { await cloud.signInWithEmailAndPassword(cloud.auth, $('accountEmail').value, $('accountPassword').value); $('accountStatus').textContent = 'Giriş başarılı.'; } catch (error) { $('accountStatus').textContent = error.code === 'auth/invalid-credential' ? 'E-posta veya şifre hatalı.' : 'Giriş başarısız. Firebase Authentication ayarlarını kontrol edin.'; } });
$('signUpButton').addEventListener('click', async () => { if (!cloud) return; $('accountStatus').textContent = 'Hesap oluşturuluyor…'; try { await cloud.createUserWithEmailAndPassword(cloud.auth, $('accountEmail').value, $('accountPassword').value); $('accountStatus').textContent = 'Hesap oluşturuldu.'; } catch { $('accountStatus').textContent = 'Hesap oluşturulamadı. En az 6 karakterli bir şifre kullanın.'; } });
$('signOutButton').addEventListener('click', async () => { if (cloud) await cloud.signOut(cloud.auth); $('accountStatus').textContent = 'Çıkış yapıldı.'; });
updateAccountUi();
initCloudAccount();
if (state.watchlist.size) $('watchlistButton').textContent = `☆ ${state.watchlist.size}`;
renderWatchlist();
loadData();
