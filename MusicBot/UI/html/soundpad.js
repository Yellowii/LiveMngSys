const state = {
  soundpad: null, devices: [], view: 'board', mode: 'play', pageId: '', selected: null, dragButtonId: '',
  collapsed: localStorage.getItem('musicbot.soundpad.collapsed') === 'true',
  columns: Math.max(3, Math.min(10, Number(localStorage.getItem('musicbot.soundpad.columns')) || 6)),
  rowHeight: Math.max(72, Math.min(200, Number(localStorage.getItem('musicbot.soundpad.rowHeight')) || 118)),
  drawerDirty: false, drawerRenderedFor: '', settingsDirty: false, playbackReceivedAt: 0,
}
const $ = (selector) => document.querySelector(selector)

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
  const result = await response.json().catch(() => ({}))
  if (!response.ok || result.ok === false) throw new Error(result.error || result.message || `HTTP ${response.status}`)
  if (result.soundpad) applyState(result.soundpad)
  return result
}
function escapeHtml(value) { return String(value || '').replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char])) }
function activePage() { return state.soundpad?.pages.find((page) => page.id === state.pageId) || state.soundpad?.pages[0] || null }
function buttonToken(buttonId) { const match = String(buttonId || '').match(/button-(\d+)$/); return match ? `B${match[1]}` : 'BTN' }
function buttonImage(button) { return button.imageFile ? `/api/soundpad/buttons/${encodeURIComponent(button.id)}/image?v=${encodeURIComponent(button.imageFile)}` : '' }
function buttonProgress(button) { const progress = button.progress; return progress?.duration ? Math.max(0, Math.min(100, progress.position / progress.duration * 100)) : 0 }
function formatTime(seconds) { const value = Math.max(0, Math.floor(Number(seconds || 0))); return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}` }

function applyState(soundpad) {
  state.soundpad = soundpad
  state.playbackReceivedAt = performance.now()
  if (!state.pageId || !soundpad.pages.some((page) => page.id === state.pageId)) state.pageId = soundpad.pages[0]?.id || ''
  render()
}
function renderPages() {
  $('#page-list').innerHTML = (state.soundpad?.pages || []).map((page) => `<button class="page-button ${page.id === state.pageId ? 'active' : ''}" data-page="${page.id}">${escapeHtml(page.name)}</button>`).join('')
  document.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => { state.pageId = button.dataset.page; state.selected = null; render() }))
}
function renderBoard() {
  const page = activePage(); if (!page) return
  $('#active-page-name').textContent = page.name
  $('#board-mode-note').textContent = state.mode === 'play' ? '单击按钮播放音效' : '单击按钮配置，拖动按钮换位'
  const grid = $('#soundpad-grid'); grid.style.setProperty('--soundpad-columns', state.columns); grid.style.setProperty('--soundpad-row-height', `${state.rowHeight}px`)
  grid.innerHTML = page.buttons.map((button) => {
    const label = button.label || button.clip?.name || '未配置'
    return `<button draggable="${state.mode === 'configure'}" class="soundpad-button ${button.active ? 'active' : ''} ${button.pending ? 'pending' : ''} ${button.clip ? '' : 'empty'}" data-button="${button.id}" style="--fill-color:${button.fillColor};--progress-color:${button.progressColor};--button-image:url('${buttonImage(button)}');--progress:${buttonProgress(button)}%"><span class="button-id">${buttonToken(button.id)}</span><span class="button-label">${escapeHtml(label)}</span></button>`
  }).join('')
  document.querySelectorAll('[data-button]').forEach((element) => {
    element.addEventListener('click', () => state.mode === 'configure' ? openDrawer(element.dataset.button) : playButton(element.dataset.button))
    element.addEventListener('dragstart', () => { state.dragButtonId = element.dataset.button; element.classList.add('dragging') })
    element.addEventListener('dragend', () => { state.dragButtonId = ''; element.classList.remove('dragging') })
    element.addEventListener('dragover', (event) => { if (state.mode === 'configure') event.preventDefault() })
    element.addEventListener('drop', async (event) => { event.preventDefault(); if (state.mode === 'configure' && state.dragButtonId) await request(`/api/soundpad/pages/${state.pageId}/reorder`, { method: 'POST', body: JSON.stringify({ sourceButtonId: state.dragButtonId, targetButtonId: element.dataset.button }) }) })
  })
}
function renderLibrary() {
  const clips = state.soundpad?.clips || []; $('#library-count').textContent = `${clips.length} 个音效`
  $('#soundpad-library').innerHTML = clips.map((clip) => `<article class="library-item"><strong>${escapeHtml(clip.name)}</strong><small>${escapeHtml(clip.path)}</small><code>${escapeHtml(clip.id)}</code></article>`).join('') || '<p>尚未导入音效文件。</p>'
}
function renderSettings() {
  const settings = state.soundpad?.settings; if (!settings || state.settingsDirty) return
  $('#master-volume').value = settings.masterVolume; $('#master-volume-value').textContent = `${settings.masterVolume}%`
  const devices = [{ name: 'auto', description: '系统默认设备' }, ...(state.devices || [])]
  $('#soundpad-device').innerHTML = devices.map((device) => `<option value="${escapeHtml(device.name)}">${escapeHtml(device.description || device.name)}</option>`).join('')
  $('#soundpad-device').value = settings.audioDevice; if (!$('#soundpad-device').value) $('#soundpad-device').value = 'auto'
  $('#external-enabled').checked = settings.externalEnabled
}
function renderDrawer() {
  const drawer = $('#config-drawer'); const open = Boolean(state.selected); drawer.classList.toggle('open', open); $('#drawer-scrim').classList.toggle('open', open); drawer.setAttribute('aria-hidden', String(!open))
  if (!open) return
  const button = activePage()?.buttons.find((item) => item.id === state.selected); if (!button) return closeDrawer()
  if (state.drawerDirty && state.drawerRenderedFor === button.id) return
  $('#drawer-button-id').textContent = button.id; $('#drawer-mapping-id').textContent = `${state.pageId}/${button.id}`
  $('#button-clip').innerHTML = `<option value="">未配置</option>${(state.soundpad.clips || []).map((clip) => `<option value="${clip.id}" ${clip.id === button.clipId ? 'selected' : ''}>${escapeHtml(clip.name)}</option>`).join('')}`
  $('#button-label').value = button.label || ''; $('#button-fill-color').value = button.fillColor || '#202a36'; $('#button-progress-color').value = button.progressColor || '#4f8cff'; $('#button-image-name').value = button.imageFile || ''
  $('#button-volume').value = button.volume ?? 100; $('#button-volume-value').textContent = `${$('#button-volume').value}%`; $('#button-delay').value = button.delayMs ?? 0; $('#button-loop-count').value = Number.isFinite(Number(button.loopCount)) ? button.loopCount : (button.loop ? -1 : 0)
  state.drawerRenderedFor = button.id
}
function renderPlayback() {
  const active = state.soundpad?.pages.flatMap((page) => page.buttons).find((button) => button.active || button.pending)
  const playback = state.soundpad?.playback || {}; const duration = Number(playback.duration || active?.progress?.duration || 0); const position = Number(playback.position || active?.progress?.position || 0)
  $('#now-playing-title').textContent = active ? (active.label || active.clip?.name || '未命名音效') : '尚未播放'
  $('#now-playing-time').textContent = `${formatTime(position)} / ${formatTime(duration)}`
  $('#playback-dot').classList.toggle('playing', Boolean(active)); $('#player-status').textContent = playback.status === 'pending' ? '等待播放' : playback.status === 'playing' ? '播放中' : '播放器待命'
}
function render() { renderPages(); renderBoard(); renderLibrary(); renderSettings(); renderDrawer(); renderPlayback(); $('#soundpad-sidebar').classList.toggle('collapsed', state.collapsed) }
function setView(view) { state.view = view; document.querySelectorAll('.side-tab').forEach((button) => button.classList.toggle('active', button.dataset.view === view)); document.querySelectorAll('.soundpad-view').forEach((section) => section.classList.toggle('active', section.id === `view-${view}`)) }
function setMode(mode) { state.mode = mode; document.querySelectorAll('[data-mode]').forEach((button) => button.classList.toggle('active', button.dataset.mode === mode)); renderBoard() }
function closeDrawer() { state.selected = null; state.drawerDirty = false; state.drawerRenderedFor = ''; renderDrawer() }
function openDrawer(buttonId) { state.selected = buttonId; state.drawerDirty = false; state.drawerRenderedFor = ''; renderDrawer() }
async function playButton(buttonId) { const button = activePage()?.buttons.find((item) => item.id === buttonId); if (!button?.clip) return; try { await request('/api/soundpad/play', { method: 'POST', body: JSON.stringify({ pageId: state.pageId, buttonId }) }) } catch (error) { showError(error) } }
function showError(error) { window.alert(error.message || String(error)) }

document.querySelectorAll('.side-tab').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)))
document.querySelectorAll('[data-mode]').forEach((button) => button.addEventListener('click', () => setMode(button.dataset.mode)))
for (const value of [9, 10]) { if (!Array.from($('#panel-columns').options).some((option) => Number(option.value) === value)) $('#panel-columns').append(new Option(`${value} 列`, String(value))) }
$('#panel-columns').value = String(state.columns); $('#panel-columns').addEventListener('change', () => { state.columns = Number($('#panel-columns').value); localStorage.setItem('musicbot.soundpad.columns', String(state.columns)); renderBoard() })
$('#row-height').value = String(state.rowHeight); $('#row-height-value').textContent = `${state.rowHeight}px`; $('#row-height').addEventListener('input', () => { state.rowHeight = Number($('#row-height').value); localStorage.setItem('musicbot.soundpad.rowHeight', String(state.rowHeight)); $('#row-height-value').textContent = `${state.rowHeight}px`; renderBoard() })
$('#toggle-sidebar').addEventListener('click', () => { state.collapsed = !state.collapsed; localStorage.setItem('musicbot.soundpad.collapsed', String(state.collapsed)); render() })
function closePageDialog() { $('#page-dialog').classList.remove('open'); $('#page-dialog').setAttribute('aria-hidden', 'true') }
$('#new-page').addEventListener('click', () => { $('#page-name-input').value = ''; $('#page-dialog').classList.add('open'); $('#page-dialog').setAttribute('aria-hidden', 'false'); $('#page-name-input').focus() })
$('#cancel-new-page').addEventListener('click', closePageDialog); $('#page-dialog').addEventListener('click', (event) => { if (event.target === $('#page-dialog')) closePageDialog() })
$('#confirm-new-page').addEventListener('click', async () => { const name = $('#page-name-input').value.trim(); if (!name) return; try { const result = await request('/api/soundpad/pages', { method: 'POST', body: JSON.stringify({ name }) }); state.pageId = result.page?.id || state.pageId; closePageDialog() } catch (error) { showError(error) } })
$('#stop-sound').textContent = '■'; $('#stop-sound').setAttribute('title', '停止全部'); $('#stop-sound').setAttribute('aria-label', '停止全部')
$('#stop-sound').addEventListener('click', () => request('/api/soundpad/stop', { method: 'POST' }).catch(showError))
$('#close-drawer').addEventListener('click', closeDrawer); $('#drawer-scrim').addEventListener('click', closeDrawer)
for (const selector of ['#button-clip', '#button-label', '#button-fill-color', '#button-progress-color', '#button-volume', '#button-delay', '#button-loop-count']) $(selector).addEventListener('input', () => { state.drawerDirty = true })
$('#button-volume').addEventListener('input', () => { $('#button-volume-value').textContent = `${$('#button-volume').value}%` })
$('#save-button').addEventListener('click', async () => { if (!state.selected) return; try { await request(`/api/soundpad/pages/${state.pageId}/buttons/${state.selected}`, { method: 'PUT', body: JSON.stringify({ clipId: $('#button-clip').value, label: $('#button-label').value.trim(), fillColor: $('#button-fill-color').value, progressColor: $('#button-progress-color').value, volume: Number($('#button-volume').value), delayMs: Number($('#button-delay').value), loopCount: Number($('#button-loop-count').value) }) }); closeDrawer() } catch (error) { showError(error) } })
$('#clear-button').addEventListener('click', async () => { if (!state.selected) return; try { await request(`/api/soundpad/pages/${state.pageId}/buttons/${state.selected}`, { method: 'PUT', body: JSON.stringify({ clipId: '', label: '', imageFile: '', delayMs: 0, loopCount: 0 }) }); closeDrawer() } catch (error) { showError(error) } })
$('#select-button-image').addEventListener('click', () => request(`/api/soundpad/pages/${state.pageId}/buttons/${state.selected}/image`, { method: 'POST' }).catch(showError))
$('#master-volume').addEventListener('input', () => { state.settingsDirty = true; $('#master-volume-value').textContent = `${$('#master-volume').value}%` }); $('#soundpad-device').addEventListener('change', () => { state.settingsDirty = true })
$('#save-settings').addEventListener('click', async () => { try { await request('/api/soundpad/settings', { method: 'PATCH', body: JSON.stringify({ masterVolume: Number($('#master-volume').value), audioDevice: $('#soundpad-device').value }) }); state.settingsDirty = false; renderSettings() } catch (error) { showError(error) } })
$('#external-enabled').addEventListener('change', () => request('/api/soundpad/settings', { method: 'PATCH', body: JSON.stringify({ externalEnabled: $('#external-enabled').checked }) }).catch(showError))
async function uploadSoundpadFiles(files) { for (const file of Array.from(files || [])) { const response = await fetch('/api/soundpad/import/upload', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Soundpad-Filename': encodeURIComponent(file.name) }, body: file }); const result = await response.json().catch(() => ({})); if (!response.ok || result.ok === false) throw new Error(result.error || result.message || `HTTP ${response.status}`); if (result.soundpad) applyState(result.soundpad) } }
$('#import-file').addEventListener('click', () => $('#audio-file-input').click()); $('#import-folder').addEventListener('click', () => $('#audio-folder-input').click())
$('#audio-file-input').addEventListener('change', async (event) => { try { await uploadSoundpadFiles(event.target.files) } catch (error) { showError(error) } finally { event.target.value = '' } }); $('#audio-folder-input').addEventListener('change', async (event) => { try { await uploadSoundpadFiles(event.target.files) } catch (error) { showError(error) } finally { event.target.value = '' } })
async function loadDevices() { try { const result = await request('/api/soundpad/devices'); state.devices = result.devices || []; renderSettings() } catch (error) { console.warn('SoundPad device enumeration failed', error) } }
async function refresh() { try { const result = await request('/api/soundpad/state'); applyState(result.soundpad) } catch (error) { $('#player-status').textContent = error.message || 'SoundPad unavailable' } }
function animateButtonProgress() {
  const playback = state.soundpad?.playback || {}; const active = state.soundpad?.pages.flatMap((page) => page.buttons).find((button) => button.active)
  if (active?.progress?.duration && playback.status === 'playing') {
    const position = Number(active.progress.position || 0) + (performance.now() - state.playbackReceivedAt) / 1000
    const percent = Math.max(0, Math.min(100, position / Number(active.progress.duration) * 100))
    document.querySelector(`[data-button="${active.id}"]`)?.style.setProperty('--progress', `${percent}%`)
  }
  requestAnimationFrame(animateButtonProgress)
}
setView('board'); refresh(); loadDevices(); window.setInterval(refresh, 500)
requestAnimationFrame(animateButtonProgress)
