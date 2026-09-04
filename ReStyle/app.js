const previewBase = `
  *{box-sizing:border-box}html,body{overflow:hidden}body{margin:0;min-height:100vh;padding:20px;display:grid;place-items:center;background-color:var(--theme-workspace-bg);background-image:url('./assets/project-dark.jpg');background-position:center;background-size:cover;color:var(--theme-text-color);font:13px/1.5 var(--body-font,"Noto Sans SC","Microsoft YaHei UI",system-ui,sans-serif)}button,input,select{font:inherit}
`;

const samples = {
  button: {
    name: '按钮', type: '基础组件', group: '基础组件', path: 'components/base/button.html', description: '主要、次要、危险与图标操作',
    html: `<div class="button-row">\n  <button class="btn primary">保存配置</button>\n  <button class="btn secondary">取消</button>\n  <button class="btn danger">停止服务</button>\n  <button class="icon-btn" title="刷新">↻</button>\n</div>`,
    css: `${previewBase}.button-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.btn,.icon-btn{height:38px;border-radius:8px;font-weight:700;cursor:pointer;transition:all .2s}.btn{padding:0 18px}.primary{color:#fff;background:var(--theme-color-active);border:0;box-shadow:0 4px 6px rgba(var(--theme-color-active-rgb),.15)}.secondary,.icon-btn{color:var(--theme-text-color);background:transparent;border:1px solid var(--theme-border-color)}.danger{color:#ef6b75;background:rgba(239,91,103,.1);border:1px solid rgba(239,91,103,.42)}.btn:hover,.icon-btn:hover{transform:translateY(-1px);filter:brightness(1.12)}.icon-btn{width:38px;font-size:18px}`,
    js: `document.querySelectorAll('button').forEach(button => {\n  button.addEventListener('click', () => {\n    button.dataset.clicked = 'true';\n  });\n});`
  },
  input: {
    name: '表单控件', type: '基础组件', group: '基础组件', path: 'components/base/form-control.html', description: '输入框、选择器、开关与滑杆',
    html: `<form class="form-grid">\n  <label>直播间 ID<input value="991263980971"></label>\n  <label>监听方式<select><option>纯签名直连</option><option>浏览器兼容</option></select></label>\n  <label class="switch-row">自动重连<input type="checkbox" checked><span class="switch"></span></label>\n  <label>刷新间隔 <output>150 ms</output><input type="range" min="50" max="1000" value="150"></label>\n</form>`,
    css: `${previewBase}body{place-items:stretch}.form-grid{width:100%;max-width:560px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}label{min-width:0;display:grid;gap:8px;color:var(--theme-text-color);font-size:13px;font-weight:700}input,select{width:100%;min-width:0;height:38px;padding:0 14px;border:1px solid var(--theme-border-color);border-radius:8px;background:var(--theme-control-bg);color:var(--theme-text-color);outline:0}input:focus,select:focus{border-color:var(--theme-color-active);box-shadow:0 0 0 3px rgba(var(--theme-color-active-rgb),.15)}.switch-row{display:flex;align-items:center;gap:8px}.switch-row input{display:none}.switch{width:32px;height:18px;padding:2px;border-radius:10px;background:var(--theme-color-active)}.switch:after{content:"";display:block;width:14px;height:14px;margin-left:14px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}output{float:right;color:var(--theme-color-active)}@media(max-width:420px){.form-grid{grid-template-columns:1fr;gap:9px}}`,
    js: `const range = document.querySelector('[type=range]');\nconst output = document.querySelector('output');\nrange.addEventListener('input', () => output.textContent = range.value + ' ms');`
  },
  badge: {
    name: '状态与徽章', type: '基础组件', group: '基础组件', path: 'components/base/status-badge.html', description: '服务状态、身份与计数标签',
    html: `<div class="badges">\n  <span class="status online"><i></i>已连接</span>\n  <span class="status waiting"><i></i>等待重启</span>\n  <span class="role">粉丝团 Lv.12</span>\n  <span class="role member">会员</span>\n  <span class="count">24</span>\n</div>`,
    css: `${previewBase}.badges{width:100%;display:flex;gap:8px;align-items:center;justify-content:center;flex-wrap:wrap}.status,.role,.count{min-height:24px;padding:0 8px;border-radius:4px;display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700}.status{border:1px solid var(--theme-border-color);background:var(--theme-control-bg);color:var(--theme-muted-text-color)}.status i{width:7px;height:7px;border-radius:50%;background:#19c37d;box-shadow:0 0 0 3px rgba(25,195,125,.15)}.waiting i{background:#f3ad35;box-shadow:0 0 0 3px rgba(243,173,53,.15)}.role{color:#64b5ff;background:rgba(77,163,255,.16)}.member{color:#c58cff;background:rgba(179,111,234,.16)}.count{min-width:24px;justify-content:center;color:#fff;background:var(--theme-color-active)}`,
    js: ``
  },
  segmented: {
    name: '分段控制器', type: '基础组件', group: '基础组件', path: 'components/base/segmented-control.html', description: '互斥视图与模式切换',
    html: `<div class="segmented" role="group">\n  <button class="active">全部</button>\n  <button>礼物</button>\n  <button>互动</button>\n  <button>观众榜</button>\n</div>`,
    css: `${previewBase}.segmented{display:flex;padding:4px;gap:4px;background:var(--theme-control-bg);border:1px solid var(--theme-border-color);border-radius:8px}.segmented button{height:32px;padding:0 12px;border:1px solid transparent;background:transparent;color:var(--theme-muted-text-color);border-radius:6px;cursor:pointer}.segmented button.active{border-color:var(--theme-color-active);background:var(--theme-color-active);color:#fff;font-weight:700}`,
    js: `document.querySelectorAll('button').forEach(button => {\n  button.onclick = () => {\n    document.querySelector('.active').classList.remove('active');\n    button.classList.add('active');\n  };\n});`
  },
  table: {
    name: '数据表格', type: '复合组件', group: '复合组件', path: 'components/compound/data-table.html', description: '成员、状态、指标与行操作',
    html: `<div class="table-wrap"><table>\n<thead><tr><th>成员</th><th>粉丝团</th><th>互动记录</th><th>状态</th><th></th></tr></thead>\n<tbody><tr><td><div class="person"><img src="./assets/avatar-sample.png"><b>星河入梦</b></div></td><td>Lv.12</td><td>弹 86 · 礼 12</td><td><span>活跃</span></td><td><button>详情</button></td></tr><tr><td><div class="person"><span class="avatar">林</span><b>林间风</b></div></td><td>Lv.8</td><td>弹 42 · 礼 3</td><td><span>在线</span></td><td><button>详情</button></td></tr></tbody>\n</table></div>`,
    css: `${previewBase}body{padding:10px;place-items:stretch}.table-wrap{width:100%;overflow:auto;background:var(--theme-card-bg);border:1px solid var(--theme-border-color);border-radius:8px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:9px 10px;border-bottom:1px solid var(--theme-border-color);text-align:left}th{background:rgba(var(--theme-color-active-rgb),.06);color:var(--theme-muted-text-color);font-size:10px}.person{display:flex;align-items:center;gap:7px}.person img,.avatar{width:26px;height:26px;border-radius:50%;object-fit:cover}.avatar{display:grid;place-items:center;background:var(--theme-control-bg);color:var(--theme-color-active)}td>span{padding:2px 6px;background:rgba(25,195,125,.15);color:#35bf77;border-radius:4px}button{padding:4px 8px;color:var(--theme-text-color);border:1px solid var(--theme-border-color);background:transparent;border-radius:6px}`,
    js: ``
  },
  monitor: {
    name: '实时监控卡', type: '复合组件', group: '复合组件', path: 'components/compound/monitor-card.html', description: '直播事件流与分类强调色',
    html: `<section class="monitor">\n<header><div><i></i><strong>实时互动</strong></div><span>24 条</span></header>\n<div class="feed">\n  <article class="gift"><b>星河入梦</b><span>送出 小心心 × 12</span><time>18:42</time></article>\n  <article class="chat"><b>林间风</b><span>今天的歌单很好听</span><time>18:41</time></article>\n  <article class="follow"><b>橙子汽水</b><span>关注了主播</span><time>18:41</time></article>\n</div></section>`,
    css: `${previewBase}body{place-items:stretch;padding:10px}.monitor{width:100%;overflow:hidden;background:var(--theme-card-bg);border:1px solid var(--theme-border-color);border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.07)}.monitor header{min-height:48px;padding:0 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--theme-border-color)}.monitor header div{display:flex;align-items:center;gap:9px}.monitor header i{width:3px;height:18px;background:#39b9ad;border-radius:2px}.monitor header span,time{color:var(--theme-muted-text-color);font-size:10.5px}.feed article{padding:9px 13px 9px 11px;border-bottom:1px solid var(--theme-border-color);border-left:3px solid transparent;display:grid;grid-template-columns:90px 1fr auto;gap:7px}.gift{border-left-color:#f0a33a!important;background:rgba(240,163,58,.24)}.chat{border-left-color:#39b9ad!important;background:rgba(57,185,173,.24)}.follow{border-left-color:#68975c!important;background:rgba(104,151,92,.24)}`,
    js: ``
  },
  modal: {
    name: '确认弹窗', type: '复合组件', group: '复合组件', path: 'components/compound/confirm-dialog.html', description: '需要明确确认的阻断操作',
    html: `<div class="backdrop"><section class="dialog">\n<header><div class="dialog-icon">!</div><div><h2>停止监听服务？</h2><p>停止后将不再接收直播间事件。</p></div></header>\n<footer><button class="secondary">取消</button><button class="danger">停止服务</button></footer>\n</section></div>`,
    css: `${previewBase}body{padding:0}.backdrop{position:fixed;inset:0;display:grid;place-items:center;background:rgba(0,0,0,.5);backdrop-filter:blur(5px)}.dialog{width:min(460px,90%);padding:28px;background:var(--theme-popup-bg);border:1px solid var(--theme-border-color);border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.4)}header{display:flex;gap:11px}.dialog-icon{width:32px;height:32px;display:grid;place-items:center;color:#ef6b75;background:rgba(239,91,103,.1);border-radius:6px;font-weight:900}h2{margin:0;font-size:17px}p{margin:4px 0;color:var(--theme-muted-text-color)}footer{margin-top:18px;display:flex;justify-content:flex-end;gap:12px}button{height:36px;padding:0 18px;border-radius:8px;font-weight:700}.secondary{color:var(--theme-text-color);background:transparent;border:1px solid var(--theme-border-color)}.danger{color:#ef6b75;background:rgba(239,91,103,.1);border:1px solid rgba(239,91,103,.42)}`,
    js: `document.querySelectorAll('button').forEach(button => {\n  button.onclick = () => document.querySelector('.dialog').style.opacity = '.55';\n});`
  },
  queue: {
    name: '点歌队列项', type: '复合组件', group: '复合组件', path: 'components/compound/music-queue-item.html', description: '歌曲、点歌人和播放状态',
    html: `<div class="queue">\n<article class="playing"><span class="index">▶</span><div><b>雨下一整晚</b><small>周杰伦 · 04:17</small></div><span class="requester">星河入梦</span><button>•••</button></article>\n<article><span class="index">02</span><div><b>如愿</b><small>王菲 · 04:25</small></div><span class="requester">林间风</span><button>•••</button></article>\n</div>`,
    css: `${previewBase}body{place-items:stretch;padding:10px}.queue{width:100%;border:1px solid #dfe5e3;border-radius:7px;overflow:hidden}.queue article{min-height:56px;padding:8px 10px;display:grid;grid-template-columns:28px 1fr auto 28px;align-items:center;gap:8px;border-bottom:1px solid #e8eceb}.queue article:last-child{border:0}.playing{background:#edf7f4}.index{color:#087f6d;font-weight:800}b,small{display:block}small{color:#8b9593}.requester{color:#66716f;font-size:10px}button{width:28px;height:28px;border:0;background:transparent}`,
    js: ``
  }
};

const projectFieldCss = `${previewBase}
.demo-field {
  width: min(250px, 100%);
  display: grid;
  gap: 8px;
}
.demo-field label {
  color: var(--theme-text-color);
  font-size: 13px;
  font-weight: 700;
}
.theme-input {
  width: 100%;
  height: 40px;
  padding: 0 14px;
  border: 1px solid var(--theme-border-color);
  border-radius: 8px;
  outline: none;
  background: var(--theme-control-bg);
  color: var(--theme-text-color);
}
.theme-input:focus {
  border-color: var(--theme-color-active);
  box-shadow: 0 0 0 3px rgba(var(--theme-color-active-rgb), .15);
}
.hint {
  color: var(--theme-muted-text-color);
  font-size: 11px;
}`;

delete samples.input;
Object.assign(samples, {
  textField: {
    name:'文本输入框', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/text-field.html', description:'单行文本与焦点状态',
    html:`<div class="demo-field">\n  <label for="room-id">直播间 ID</label>\n  <input id="room-id" class="theme-input" value="991263980971">\n  <span class="hint">支持直播间 ID 或短链</span>\n</div>`, css:projectFieldCss, js:''
  },
  autocomplete: {
    name:'自动完成输入框', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/autocomplete.html', description:'输入建议与键盘选择',
    html:`<div class="autocomplete">\n  <input class="theme-input" value="周杰">\n  <div class="suggestions">\n    <button class="active">周杰伦</button>\n    <button>周杰伦 - 晴天</button>\n    <button>周杰伦 - 搁浅</button>\n  </div>\n</div>`,
    css:`${projectFieldCss}.autocomplete{position:relative;width:min(250px,100%)}.suggestions{position:absolute;z-index:2;top:46px;right:0;left:0;padding:5px;border:1px solid var(--theme-border-color);border-radius:8px;background:var(--theme-popup-bg);box-shadow:0 12px 30px rgba(0,0,0,.28)}.suggestions button{width:100%;padding:7px 9px;border:0;border-radius:5px;background:transparent;color:var(--theme-muted-text-color);text-align:left}.suggestions button.active{background:rgba(var(--theme-color-active-rgb),.16);color:var(--theme-text-color)}`,
    js:`document.querySelectorAll('.suggestions button').forEach(button => {\n  button.addEventListener('click', () => {\n    document.querySelector('.theme-input').value = button.textContent;\n  });\n});`
  },
  select: {
    name:'选择器', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/select.html', description:'单选下拉列表',
    html:`<div class="demo-field">\n  <label for="transport">监听方式</label>\n  <select id="transport" class="theme-input">\n    <option>纯签名直连</option>\n    <option>浏览器兼容</option>\n  </select>\n</div>`, css:projectFieldCss, js:''
  },
  checkbox: {
    name:'复选框', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/checkbox.html', description:'独立或批量选择',
    html:`<label class="check">\n  <input type="checkbox" checked>\n  <span></span>\n  <b>同步礼物特效资源</b>\n</label>`,
    css:`${previewBase}.check{display:flex;align-items:center;gap:9px;color:var(--theme-text-color);cursor:pointer}.check input{position:absolute;opacity:0}.check span{width:19px;height:19px;border:1px solid var(--theme-border-color);border-radius:4px;background:var(--theme-control-bg);display:grid;place-items:center}.check input:checked+span{border-color:var(--theme-color-active);background:var(--theme-color-active)}.check input:checked+span:after{content:'✓';color:#fff;font-size:13px;font-weight:900}.check b{font-size:13px}`,
    js:''
  },
  switch: {
    name:'开关', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/switch.html', description:'二元配置状态',
    html:`<label class="switch-row">\n  <span>自动重连</span>\n  <input type="checkbox" checked>\n  <i></i>\n</label>`,
    css:`${previewBase}.switch-row{width:min(250px,100%);min-height:42px;padding:9px 11px;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--theme-border-color);border-radius:7px;background:rgba(var(--theme-color-active-rgb),.035);color:var(--theme-text-color);cursor:pointer}.switch-row input{position:absolute;opacity:0}.switch-row i{width:32px;height:18px;position:relative;border-radius:10px;background:rgba(125,132,151,.42)}.switch-row i:after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:#fff;transition:.2s}.switch-row input:checked+i{background:var(--theme-color-active)}.switch-row input:checked+i:after{transform:translateX(14px)}`,
    js:''
  },
  radioGroup: {
    name:'单选组', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/radio-group.html', description:'互斥选项集合',
    html:`<fieldset class="radio-group">\n  <legend>输出模式</legend>\n  <label><input type="radio" name="mode" checked><span></span>字幕</label>\n  <label><input type="radio" name="mode"><span></span>公告</label>\n  <label><input type="radio" name="mode"><span></span>关闭</label>\n</fieldset>`,
    css:`${previewBase}.radio-group{padding:0;border:0;display:grid;gap:10px;color:var(--theme-text-color)}legend{margin-bottom:10px;color:var(--theme-muted-text-color);font-size:11px}.radio-group label{display:flex;align-items:center;gap:8px}.radio-group input{position:absolute;opacity:0}.radio-group label span{width:18px;height:18px;border:1px solid var(--theme-border-color);border-radius:50%;background:var(--theme-control-bg)}.radio-group input:checked+span{border:5px solid var(--theme-color-active)}`,
    js:''
  },
  slider: {
    name:'滑杆', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/slider.html', description:'连续数值调整',
    html:`<div class="range-field">\n  <div><label for="refresh">刷新间隔</label><output>150 ms</output></div>\n  <input id="refresh" type="range" min="50" max="1000" value="150">\n</div>`,
    css:`${previewBase}.range-field{width:min(270px,100%);display:grid;gap:12px}.range-field div{display:flex;justify-content:space-between;color:var(--theme-text-color)}output{color:var(--theme-color-active);font:11px var(--code-font,monospace)}input[type=range]{width:100%;accent-color:var(--theme-color-active)}`,
    js:`const range = document.querySelector('input');\nrange.addEventListener('input', () => {\n  document.querySelector('output').textContent = range.value + ' ms';\n});`
  },
  numberInput: {
    name:'数字步进器', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/number-stepper.html', description:'离散数值增减',
    html:`<div class="stepper">\n  <button data-step="-1">−</button>\n  <input value="150" inputmode="numeric">\n  <button data-step="1">＋</button>\n  <span>ms</span>\n</div>`,
    css:`${previewBase}.stepper{display:grid;grid-template-columns:34px 78px 34px auto;align-items:center}.stepper button,.stepper input{height:36px;border:1px solid var(--theme-border-color);background:var(--theme-control-bg);color:var(--theme-text-color);text-align:center}.stepper button:first-child{border-radius:7px 0 0 7px}.stepper button:nth-child(3){border-radius:0 7px 7px 0}.stepper input{border-right:0;border-left:0}.stepper span{margin-left:8px;color:var(--theme-muted-text-color)}`,
    js:`document.querySelectorAll('button').forEach(button => {\n  button.onclick = () => {\n    const input = document.querySelector('input');\n    input.value = Number(input.value) + Number(button.dataset.step);\n  };\n});`
  },
  textarea: {
    name:'多行文本框', type:'基础组件', group:'基础组件', category:'输入控件', source:'SparkFlow', path:'components/inputs/textarea.html', description:'文案与长文本编辑',
    html:`<div class="demo-field">\n  <label for="message">私信文案</label>\n  <textarea id="message" class="theme-input">今晚八点直播间见</textarea>\n  <span class="counter">9 / 200</span>\n</div>`,
    css:`${projectFieldCss}.demo-field{position:relative}.theme-input{height:92px;padding-top:10px;resize:none}.counter{position:absolute;right:9px;bottom:8px;color:var(--theme-muted-text-color);font:10px var(--code-font,monospace)}`,
    js:`const textarea = document.querySelector('textarea');\ntextarea.addEventListener('input', () => {\n  document.querySelector('.counter').textContent = textarea.value.length + ' / 200';\n});`
  },
  colorInput: {
    name:'颜色输入框', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/color-input.html', description:'颜色值与色板同步',
    html:`<div class="color-input">\n  <input type="color" value="#3a6df0">\n  <input class="theme-input" value="#3a6df0">\n</div>`,
    css:`${projectFieldCss}.color-input{width:min(230px,100%);display:grid;grid-template-columns:40px 1fr;gap:8px}.color-input input[type=color]{width:40px;height:40px;padding:3px;border:1px solid var(--theme-border-color);border-radius:8px;background:var(--theme-control-bg)}`,
    js:`const picker = document.querySelector('[type=color]');\nconst text = document.querySelector('.theme-input');\npicker.oninput = () => text.value = picker.value;`
  },
  searchInput: {
    name:'搜索框', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/search.html', description:'筛选组件或用户数据',
    html:`<label class="search-input">\n  <span>⌕</span>\n  <input placeholder="搜索昵称、抖音号或标签">\n  <kbd>/</kbd>\n</label>`,
    css:`${previewBase}.search-input{width:min(310px,100%);height:40px;padding:0 10px;display:flex;align-items:center;gap:8px;border:1px solid var(--theme-border-color);border-radius:8px;background:var(--theme-control-bg);color:var(--theme-muted-text-color)}.search-input input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:var(--theme-text-color)}kbd{padding:2px 5px;border:1px solid var(--theme-border-color);border-radius:4px;font:10px var(--code-font,monospace)}`,
    js:''
  },
  fileUpload: {
    name:'文件上传', type:'基础组件', group:'基础组件', category:'输入控件', source:'GUIDemo', path:'components/inputs/file-upload.html', description:'点击选择或拖入文件',
    html:`<label class="upload">\n  <input type="file">\n  <b>＋</b>\n  <strong>选择配置文件</strong>\n  <span>JSON · 最大 5 MB</span>\n</label>`,
    css:`${previewBase}.upload{width:min(280px,100%);min-height:126px;padding:18px;display:grid;place-items:center;align-content:center;gap:5px;border:2px dashed var(--theme-color-active);border-radius:8px;background:rgba(var(--theme-color-active-rgb),.03);color:var(--theme-text-color);cursor:pointer}.upload input{display:none}.upload b{font-size:24px;color:var(--theme-color-active)}.upload span{color:var(--theme-muted-text-color);font-size:10px}`,
    js:''
  }
});

samples.button.category = '操作控件';
samples.badge.category = '数据展示';
samples.segmented.category = '输入控件';
samples.table.category = '数据展示';
samples.monitor.category = '直播业务';
samples.modal.category = '反馈组件';
samples.queue.category = '直播业务';

const layouts = [
  { name:'管理台布局', desc:'固定侧边栏 + 吸顶顶栏 + 可滚动内容区', diagram:'app', parts:['侧边栏 244px','顶栏 58px','内容区 minmax(0, 1fr)'] },
  { name:'聚焦工作区', desc:'轻顶栏 + 单列沉浸内容，适合回放与配置', diagram:'focus', parts:['顶栏','主工作区'] },
  { name:'主从分栏', desc:'列表/筛选在左，详情或实时画布在右', diagram:'split', parts:['资源列表 360px','详情区 1fr'] },
  { name:'直播画布', desc:'深色全屏画布 + 低干扰悬浮控制', diagram:'canvas', parts:['安全区','直播叠加层'] }
];

const projectTokenDefaults = [
  {name:'深色背景', key:'--theme-bg-color', value:'rgba(16, 18, 27, 0.10)', group:'背景', desc:'应用玻璃层底色', type:'text', enum:'rgba()：透明叠加；颜色值：纯色'},
  {name:'边框色', key:'--border-color', value:'rgba(113, 119, 144, 0.25)', group:'边框', desc:'通用分隔线', type:'text', enum:'rgba()：半透明边框'},
  {name:'主题文字', key:'--theme-color', value:'#f9fafb', group:'文字', desc:'默认前景色', type:'color'},
  {name:'非激活文字', key:'--inactive-color', value:'rgba(180, 188, 208, 0.8)', group:'文字', desc:'次要导航文字', type:'text'},
  {name:'主题激活色', key:'--theme-color-active', value:'#3a6df0', group:'主题', desc:'按钮、选中态、强调线', type:'color', enum:'蓝 #3a6df0；绿 #00b074；紫 #7f56da'},
  {name:'激活色 RGB', key:'--theme-color-active-rgb', value:'58, 109, 240', group:'主题', desc:'供 rgba(var()) 使用', type:'text'},
  {name:'侧栏模糊', key:'--sidebar-blur', value:'34px', group:'尺寸', desc:'侧栏 backdrop-filter', type:'text'},
  {name:'顶栏模糊', key:'--header-blur', value:'32px', group:'尺寸', desc:'顶栏 backdrop-filter', type:'text'},
  {name:'卡片圆角', key:'--card-radius', value:'12px', group:'尺寸', desc:'卡片统一圆角', type:'text', enum:'px：固定圆角；0：直角'},
  {name:'导航背景', key:'--theme-nav-bg', value:'rgba(16, 18, 27, 0.04)', group:'层级', desc:'侧栏导航层', type:'text'},
  {name:'工作区背景', key:'--theme-workspace-bg', value:'rgba(16, 18, 27, 0.78)', group:'层级', desc:'主工作区层', type:'text'},
  {name:'顶栏背景', key:'--theme-header-bg', value:'rgba(16, 18, 27, 0.04)', group:'层级', desc:'顶栏玻璃层', type:'text'},
  {name:'卡片背景', key:'--theme-card-bg', value:'rgba(12, 15, 25, 0.35)', group:'层级', desc:'卡片玻璃层', type:'text'},
  {name:'控件背景', key:'--theme-control-bg', value:'#14162b', group:'层级', desc:'输入框和控件', type:'color'},
  {name:'弹窗背景', key:'--theme-popup-bg', value:'rgb(22, 25, 37)', group:'层级', desc:'模态窗背景', type:'text'},
  {name:'主题文字变量', key:'--theme-text-color', value:'#f9fafb', group:'文字', desc:'组件内主文字', type:'color'},
  {name:'次要文字变量', key:'--theme-muted-text-color', value:'rgba(180, 188, 208, 0.8)', group:'文字', desc:'组件内次要文字', type:'text'},
  {name:'状态文字', key:'--header-status-text-color', value:'#f9fafb', group:'文字', desc:'顶栏状态文字', type:'color'},
  {name:'字体族', key:'--body-font', value:'"Noto Sans SC", "Microsoft YaHei UI", sans-serif', group:'字体', desc:'现有项目中文界面字体', type:'text'},
  {name:'代码字体', key:'--code-font', value:'"Cascadia Code", "JetBrains Mono", Consolas, monospace', group:'字体', desc:'编辑器与原始字段字体', type:'text'}
];
const tokenValues = JSON.parse(localStorage.getItem('livemngsys-wss-tokens') || '{}');
const tokens = projectTokenDefaults.map(token => ({...token, value: tokenValues[token.key] ?? token.value}));
const colors = tokens.filter(token => token.type === 'color').map(token => [token.name, token.value]);
const tokenRows = tokens.map(token => [token.name, token.key, token.value, token.desc]);

const state = {
  view: 'overview', query: '', componentFilter: 'all', activeSample: null, activeCode: 'html', previewZoom: 1, editor: {html:'',css:'',js:''}, originals: null,
  saved: JSON.parse(localStorage.getItem('livemngsys-wss-tree') || '{}')
};

const main = document.getElementById('mainContent');
const titleMap = {overview:'总览',layouts:'全局布局',components:'可复用组件',tokens:'设计令牌',patterns:'交互模式',tree:'项目树'};
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const projectTokenCss = () => `:root {\n${tokens.map(token => `  ${token.key}: ${token.value};`).join('\n')}\n}`;
const previewInspectorScript = sample => {
  const htmlLines = JSON.stringify(sample.html.split('\n')).replace(/</g, '\\u003c');
  return `(() => {
    const sourceLines = ${htmlLines};
    const lineMap = [];
    sourceLines.forEach((line, lineIndex) => {
      const tags = line.match(/<\\/?[A-Za-z][\\w-]*(?:\\s[^<>]*?)?\\/?>/g) || [];
      tags.forEach(tag => { if (!/^<\\//.test(tag) && !/\\/\\s*>$/.test(tag)) lineMap.push(lineIndex); });
    });
    const elements = [...document.body.querySelectorAll('*')];
    elements.forEach((element, index) => {
      if (lineMap[index] !== undefined) element.dataset.restyleLine = lineMap[index];
    });
    let active;
    const clear = () => { if (active) active.removeAttribute('data-restyle-hover'); active = null; };
    const select = line => {
      clear();
      if (line === null || line === undefined) return;
      active = document.querySelector('[data-restyle-line="' + line + '"]');
      if (active) active.setAttribute('data-restyle-hover', 'true');
    };
    const style = document.createElement('style');
    style.textContent = '[data-restyle-hover="true"]{outline:2px solid #ff9f43 !important;outline-offset:2px !important;box-shadow:0 0 0 4px rgba(255,159,67,.22) !important;}';
    document.head.appendChild(style);
    document.addEventListener('mouseover', event => {
      const element = event.target.closest?.('[data-restyle-line]');
      if (!element) return;
      select(element.dataset.restyleLine);
      parent.postMessage({source:'restyle-preview', type:'element-hover', line:Number(element.dataset.restyleLine)}, '*');
    });
    document.addEventListener('mouseout', event => {
      if (active && event.relatedTarget && active.contains(event.relatedTarget)) return;
      clear();
      parent.postMessage({source:'restyle-preview', type:'element-hover', line:null}, '*');
    });
    window.addEventListener('message', event => {
      if (event.data?.source !== 'restyle-editor' || event.data.type !== 'line-hover') return;
      select(event.data.line);
    });
  })();`;
};
const previewDocument = sample => `<!doctype html><html><head><meta charset="UTF-8"><style>${projectTokenCss()}\n${sample.css}</style></head><body>${sample.html}<script>${sample.js}<\/script><script>${previewInspectorScript(sample)}<\/script></body></html>`;
const iconRefresh = () => window.lucide && lucide.createIcons({attrs:{'stroke-width':1.8}});

function pageHead(title, description, tools = '') {
  return `<div class="page-head"><div><h1>${title}</h1><p>${description}</p></div>${tools ? `<div class="page-tools">${tools}</div>` : ''}</div>`;
}

function componentCard([id, sample]) {
  return `<article class="component-card" data-search="${escapeHtml(sample.name + sample.description + sample.type)}"><div class="component-preview"><iframe title="${escapeHtml(sample.name)}预览" data-preview="${id}" sandbox="allow-scripts"></iframe></div><div class="component-meta"><div><h3>${escapeHtml(sample.name)}</h3><p>${escapeHtml(sample.description)}</p></div><span class="spec-badge">${escapeHtml(sample.source || 'LiveMngSys')}</span><button class="edit-btn" data-edit="${id}" title="编辑${escapeHtml(sample.name)}" aria-label="编辑${escapeHtml(sample.name)}"><i data-lucide="pencil"></i></button></div></article>`;
}

function filteredSamples() {
  const query = state.query.trim().toLowerCase();
  return Object.entries(samples).filter(([, s]) => (state.componentFilter === 'all' || s.group === state.componentFilter) && (!query || `${s.name} ${s.description} ${s.type}`.toLowerCase().includes(query)));
}

function renderOverview() {
  const entries = filteredSamples().slice(0, 6);
  main.innerHTML = pageHead('前端样式系统', '从现有 LiveMngSys 界面提炼的布局、组件、令牌与交互规范。', `<button class="secondary-btn" data-nav="tokens"><i data-lucide="palette"></i>查看令牌</button>`)
    + `<section class="metric-grid"><article class="metric"><header>全局布局<span><i data-lucide="panels-top-left"></i></span></header><strong>4</strong><small>管理台 / 聚焦 / 分栏 / 直播</small></article><article class="metric"><header>可复用组件<span><i data-lucide="blocks"></i></span></header><strong>${Object.keys(samples).length}</strong><small>当前项目已提炼的预览样例</small></article><article class="metric"><header>设计令牌<span><i data-lucide="swatch-book"></i></span></header><strong>${tokens.length}</strong><small>来自 GUIDemo :root</small></article><article class="metric"><header>已保存产物<span><i data-lucide="folder-check"></i></span></header><strong>${Object.keys(state.saved).length}</strong><small>浏览器本地项目树</small></article></section>`
    + `<div class="section-head"><h2>推荐组件</h2><span>点击编辑进入实时工作台</span></div><section class="component-grid">${entries.map(componentCard).join('')}</section>`
    + `<div class="section-head"><h2>统一化建议</h2><span>从当前前端差异归纳</span></div><section class="pattern-list"><article class="pattern-item"><span><i data-lucide="variable"></i></span><div><h3>语义令牌优先</h3><p>页面不直接使用主题色值，统一映射到 canvas、surface、text、border 与状态色。</p></div></article><article class="pattern-item"><span><i data-lucide="scan-line"></i></span><div><h3>密度分级</h3><p>管理页使用紧凑密度，直播画布使用舒展密度，不通过页面级随意字号覆盖。</p></div></article></section>`;
  bindRenderedContent(entries);
}

function renderLayouts() {
  main.innerHTML = pageHead('全局布局', '定义导航、顶栏、内容区和专注工作区的稳定尺寸与响应式行为。') + `<section class="layout-grid">${layouts.map((item, index) => `<article class="layout-card"><div class="layout-card-head"><div><h3>${item.name}</h3><p>${item.desc}</p></div><button class="edit-btn" data-layout-edit="${index}" title="编辑布局"><i data-lucide="pencil"></i></button></div><div class="layout-diagram diagram-${item.diagram}">${item.parts.map((part,i)=>`<span class="${item.diagram==='app'&&i===0?'d-side':''}">${part}</span>`).join('')}</div></article>`).join('')}</section>`;
  document.querySelectorAll('[data-layout-edit]').forEach(button => button.onclick = () => openLayoutEditor(layouts[Number(button.dataset.layoutEdit)]));
  iconRefresh();
}

function renderComponents() {
  const entries = filteredSamples();
  main.innerHTML = pageHead('可复用组件', '按基础组件与复合组件分类，每个条目都可独立编辑、预览并保存。', `<div class="segmented"><button class="${state.componentFilter==='all'?'active':''}" data-filter="all">全部</button><button class="${state.componentFilter==='基础组件'?'active':''}" data-filter="基础组件">基础组件</button><button class="${state.componentFilter==='复合组件'?'active':''}" data-filter="复合组件">复合组件</button></div>`)
    + (entries.length ? componentSections(entries) : `<div class="empty-state"><div><i data-lucide="search-x"></i><p>没有匹配的组件</p></div></div>`);
  document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { state.componentFilter = button.dataset.filter; render(); });
  bindRenderedContent(entries);
}

function componentSections(entries) {
  const grouped = entries.reduce((result, entry) => {
    const category = entry[1].category || entry[1].type;
    (result[category] ||= []).push(entry);
    return result;
  }, {});
  const categoryOrder = ['输入控件', '操作控件', '数据展示', '反馈组件', '直播业务'];
  return Object.entries(grouped).sort(([left], [right]) => categoryOrder.indexOf(left) - categoryOrder.indexOf(right)).map(([category, items]) => `<section class="component-category"><div class="section-head"><h2>${escapeHtml(category)}</h2><span>${items.length} 个独立组件</span></div><div class="component-grid">${items.map(componentCard).join('')}</div></section>`).join('');
}

function renderTokens() {
  const groups = [...new Set(tokens.map(token => token.group))];
  main.innerHTML = pageHead('设计令牌', '当前项目 :root 全局变量的可编辑镜像，修改后会即时进入所有组件预览。', `<button class="secondary-btn" id="resetTokens"><i data-lucide="rotate-ccw"></i>恢复项目值</button><button class="secondary-btn" id="copyTokens"><i data-lucide="copy"></i>复制 :root</button><button class="primary-btn" id="saveTokens"><i data-lucide="save"></i>保存令牌</button>`)
    + `<div class="token-intro"><strong>设计令牌与 :root 的关系：</strong>本项目当前主要以 <code>:root</code> CSS 自定义属性承载全局令牌。令牌是“颜色/尺寸的语义约定”，<code>:root</code> 只是它在 CSS 中的一种实现载体；以后也可以同步生成 JS 常量或 JSON。</div>`
    + groups.map(group => `<section class="token-section"><div class="section-head"><h2>${group}</h2><span>${tokens.filter(token => token.group === group).length} 项 · 来源 GUIDemo/style.css</span></div><div class="token-editor-grid">${tokens.filter(token => token.group === group).map(tokenEditorMarkup).join('')}</div></section>`).join('');
  document.querySelectorAll('[data-token-key]').forEach(input => input.addEventListener('input', updateTokenFromInput));
  document.querySelectorAll('[data-token-color]').forEach(input => input.addEventListener('input', event => {
    const textInput = document.querySelector(`[data-token-key="${event.target.dataset.tokenColor}"]`);
    textInput.value = event.target.value;
    textInput.dispatchEvent(new Event('input', {bubbles:true}));
  }));
  document.getElementById('copyTokens').onclick = copyTokens;
  document.getElementById('saveTokens').onclick = saveTokens;
  document.getElementById('resetTokens').onclick = resetTokens;
  iconRefresh();
}

function tokenEditorMarkup(token) {
  const colorInput = token.type === 'color' ? `<input type="color" value="${escapeHtml(token.value)}" data-token-color="${escapeHtml(token.key)}" title="选择颜色">` : '';
  return `<article class="token-editor"><header><div><strong>${token.name}</strong><small>${token.desc}</small></div><code>${token.key}</code></header><div class="token-field ${colorInput ? '' : 'no-swatch'}">${colorInput}<input type="text" value="${escapeHtml(token.value)}" data-token-key="${escapeHtml(token.key)}" aria-label="${token.name}"></div>${token.enum ? `<div class="token-enum">可用值：${token.enum}</div>` : ''}</article>`;
}

function updateTokenFromInput(event) {
  const token = tokens.find(item => item.key === event.target.dataset.tokenKey);
  if (!token) return;
  token.value = event.target.value;
  const color = document.querySelector(`[data-token-color="${token.key}"]`);
  if (color && /^#[0-9a-f]{6}$/i.test(token.value)) color.value = token.value;
  document.querySelectorAll(`iframe[data-preview]`).forEach(frame => {
    const sample = samples[frame.dataset.preview];
    if (sample) frame.srcdoc = previewDocument(sample);
  });
}

function saveTokens() {
  localStorage.setItem('livemngsys-wss-tokens', JSON.stringify(Object.fromEntries(tokens.map(token => [token.key, token.value]))));
  toast('设计令牌已保存，组件预览将继续使用当前值');
}

function resetTokens() {
  projectTokenDefaults.forEach(defaultToken => {
    const token = tokens.find(item => item.key === defaultToken.key);
    if (token) token.value = defaultToken.value;
  });
  localStorage.removeItem('livemngsys-wss-tokens');
  renderTokens();
  toast('已恢复 GUIDemo 当前项目值');
}

function renderPatterns() {
  const patterns = [
    ['route','导航与状态保持','使用 URL hash 或持久化状态保留当前主视图和子视图，刷新后不跳回首页。'],
    ['refresh-cw','轮询与实时推送','WebSocket 承担实时事件，轮询负责快照兜底；请求使用序号保护避免旧响应覆盖。'],
    ['panel-right-open','抽屉与详情','不打断主任务的记录详情使用右侧抽屉；高风险确认才使用模态弹窗。'],
    ['list-filter','筛选与批量操作','筛选器贴近结果列表，选中条目后再显示批量工具栏。'],
    ['message-square-warning','状态与错误反馈','局部操作使用行内状态；跨页面结果使用短时 Toast；错误保留可重试入口。'],
    ['accessibility','可访问性','图标按钮提供 title/aria-label，交互元素保留键盘焦点，颜色状态同时带文本。']
  ];
  main.innerHTML = pageHead('交互模式', '从直播监听、配置、回放和队列管理流程中提炼的统一行为。') + `<section class="pattern-list">${patterns.map(p=>`<article class="pattern-item" data-search="${p[1]} ${p[2]}"><span><i data-lucide="${p[0]}"></i></span><div><h3>${p[1]}</h3><p>${p[2]}</p></div></article>`).join('')}</section>`;
  iconRefresh();
}

function renderTree() {
  const paths = Object.keys(state.saved).sort();
  const selected = paths[0];
  main.innerHTML = pageHead('项目树', '编辑器保存的组件存放在浏览器本地空间，可导出为 JSON 交付给项目。', paths.length ? `<button class="secondary-btn" id="exportTree"><i data-lucide="download"></i>导出 JSON</button>` : '')
    + `<section class="tree-panel"><aside class="tree-sidebar"><header><strong>ReStyle / saved</strong><span>${paths.length} 文件</span></header><div class="tree-files">${treeMarkup(paths)}</div></aside><div class="tree-detail" id="treeDetail">${selected ? treeDetailMarkup(selected) : `<div class="empty-state"><div><i data-lucide="folder-open"></i><p>尚未保存组件<br><small>从任一预览进入编辑器并保存</small></p></div></div>`}</div></section>`;
  document.querySelectorAll('.tree-file').forEach(button => button.onclick = () => { document.querySelectorAll('.tree-file').forEach(x=>x.classList.remove('active')); button.classList.add('active'); document.getElementById('treeDetail').innerHTML = treeDetailMarkup(button.dataset.path); bindTreeDetail(button.dataset.path); iconRefresh(); });
  if(selected) bindTreeDetail(selected);
  if(paths.length) document.getElementById('exportTree').onclick = exportTree;
  iconRefresh();
}

function treeMarkup(paths) {
  if(!paths.length) return '<span style="color:var(--color-text-faint)">空目录</span>';
  const groups = {};
  paths.forEach(path => { const folder = path.split('/').slice(0,-1).join('/') || '.'; (groups[folder] ||= []).push(path); });
  return Object.entries(groups).map(([folder, files]) => `<div class="tree-folder">▾ ${escapeHtml(folder)}</div>${files.map((path,i)=>`<button class="tree-file ${!i&&folder===Object.keys(groups)[0]?'active':''}" data-path="${escapeHtml(path)}">${escapeHtml(path.split('/').pop())}</button>`).join('')}`).join('');
}

function treeDetailMarkup(path) {
  const file = state.saved[path];
  return `<div class="page-head"><div><h1 style="font-size:16px">${escapeHtml(file.name)}</h1><p>${escapeHtml(path)} · ${new Date(file.updatedAt).toLocaleString('zh-CN')}</p></div><button class="primary-btn" data-tree-edit="${escapeHtml(path)}"><i data-lucide="pencil"></i>继续编辑</button></div><pre>${escapeHtml(file.html)}</pre>`;
}
function bindTreeDetail(path) { const button = document.querySelector('[data-tree-edit]'); if(button) button.onclick = () => openSaved(path); }

function bindRenderedContent(entries) {
  document.querySelectorAll('[data-edit]').forEach(button => button.onclick = () => openEditor(button.dataset.edit));
  document.querySelectorAll('[data-nav]').forEach(button => button.onclick = () => navigate(button.dataset.nav));
  requestAnimationFrame(() => entries.forEach(([id,sample]) => { const frame=document.querySelector(`iframe[data-preview="${id}"]`); if(frame) frame.srcdoc=previewDocument(sample); }));
  iconRefresh();
}

function render() {
  document.getElementById('breadcrumbTitle').textContent = titleMap[state.view];
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === state.view));
  ({overview:renderOverview,layouts:renderLayouts,components:renderComponents,tokens:renderTokens,patterns:renderPatterns,tree:renderTree}[state.view])();
  main.focus({preventScroll:true});
}

function navigate(view) { state.view = view; location.hash = view; render(); document.getElementById('sidebar').classList.remove('open'); }

function openEditor(id) {
  const sample = samples[id];
  state.activeSample = id;
  state.editor = {
    html: formatCode(sample.html, 'html'),
    css: formatCode(sample.css, 'css'),
    js: formatCode(sample.js, 'js')
  };
  state.originals = {...state.editor};
  state.previewZoom = 1;
  document.getElementById('editorTitle').value = sample.name;
  document.getElementById('editorType').textContent = sample.type;
  document.getElementById('editorPath').value = sample.path;
  state.activeCode = 'html';
  document.querySelectorAll('.code-tabs button').forEach(b => b.classList.toggle('active', b.dataset.code === 'html'));
  syncCodeEditor();
  document.getElementById('editorLayer').classList.add('open');
  document.getElementById('editorLayer').setAttribute('aria-hidden','false');
  document.body.style.overflow = 'hidden';
  refreshPreview(); applyPreviewZoom(); iconRefresh();
}

function openLayoutEditor(layout) {
  const id = `layout-${layout.diagram}`;
  samples[id] = { name:layout.name, type:'全局布局', group:'布局', path:`layouts/${layout.diagram}.html`, description:layout.desc,
    html:`<div class="shell ${layout.diagram}">\n  ${layout.parts.map((part,i)=>`<section class="part part-${i+1}">${part}</section>`).join('\n  ')}\n</div>`,
    css:`${previewBase}body{place-items:stretch;padding:12px;background:#eef1f0}.shell{width:100%;min-height:calc(100vh - 24px);display:grid;gap:6px}.part{display:grid;place-items:center;background:#fff;border:1px solid #d6dfdc;border-radius:5px;color:#66716f}.app{grid-template:52px 1fr / 190px 1fr}.app .part-1{grid-row:1/3;background:#18312d;color:#dce8e5}.split{grid-template-columns:360px 1fr}.focus{grid-template-rows:58px 1fr}.canvas{padding:32px;background:#17211f}.canvas .part{background:#263a36;color:#dce8e5;border-color:#36504a}`,
    js:'' };
  openEditor(id);
}

function openSaved(path) {
  const saved = state.saved[path];
  const id = `saved-${Date.now()}`;
  samples[id] = {name:saved.name,type:saved.type,group:saved.type,path,description:'已保存组件',html:saved.html,css:saved.css,js:saved.js};
  openEditor(id);
}

function closeEditor() { document.getElementById('editorLayer').classList.remove('open'); document.getElementById('editorLayer').setAttribute('aria-hidden','true'); document.body.style.overflow=''; }

function formatCode(code, type) {
  if (!code.trim()) return '';
  if (type === 'css') return formatCss(code);
  if (type === 'html') return formatHtml(code);
  return formatJavaScript(code);
}

function formatHtml(code) {
  const tokens = code.replace(/>\s*</g, '><').match(/<[^>]+>|[^<]+/g) || [];
  const voidTags = /^(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)$/i;
  let depth = 0;
  const lines = [];
  tokens.forEach(token => {
    const value = token.trim();
    if (!value) return;
    const closing = /^<\//.test(value);
    const name = value.match(/^<\/?([\w-]+)/)?.[1] || '';
    if (closing) depth = Math.max(0, depth - 1);
    lines.push(`${'  '.repeat(depth)}${value}`);
    if (!closing && /^</.test(value) && !/\/$/.test(value.slice(0, -1)) && !voidTags.test(name) && !/^<!/.test(value)) depth += 1;
  });
  return lines.join('\n');
}

function formatCss(code) {
  const expanded = code.trim()
    .replace(/\s*{\s*/g, ' {\n')
    .replace(/;\s*/g, ';\n')
    .replace(/\s*}\s*/g, '\n}\n')
    .replace(/,\s*(?=[.#\[])/g, ',\n');
  let depth = 0;
  return expanded.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    if (line.startsWith('}')) depth = Math.max(0, depth - 1);
    const formatted = `${'  '.repeat(depth)}${line}`;
    if (line.endsWith('{')) depth += 1;
    return formatted;
  }).join('\n');
}

function formatJavaScript(code) {
  if (code.includes('\n')) return code.trim().split('\n').map(line => line.replace(/\s+$/g, '')).join('\n');
  return code.trim().replace(/;\s*/g, ';\n').replace(/\{\s*/g, '{\n').replace(/\s*}/g, '\n}');
}

function highlightCode(code, type) {
  return code.split('\n').map((line, index) => `<span class="code-line" data-line="${index}">${highlightLine(line, type) || ' '}</span>`).join('');
}

function highlightHtmlTag(tag) {
  const parts = tag.match(/^(<\/?)([\w-]+)([\s\S]*?)(\/?>)$/);
  if (!parts) return escapeHtml(tag);
  const attributes = escapeHtml(parts[3]).replace(
    /(\s+)([:\w-]+)(\s*=\s*)(&quot;.*?&quot;|&#039;.*?&#039;|[^\s]+)/g,
    '$1<span class="syn-attr">$2</span>$3<span class="syn-string">$4</span>'
  );
  return `${escapeHtml(parts[1])}<span class="syn-tag">${escapeHtml(parts[2])}</span>${attributes}${escapeHtml(parts[4])}`;
}

function highlightHtmlLine(line) {
  const tagPattern = /<\/?[\w-]+(?:\s[^<>]*?)?\/?>/g;
  let result = '';
  let cursor = 0;
  let match;
  while ((match = tagPattern.exec(line))) {
    result += escapeHtml(line.slice(cursor, match.index));
    result += highlightHtmlTag(match[0]);
    cursor = match.index + match[0].length;
  }
  return result + escapeHtml(line.slice(cursor));
}

function highlightLine(line, type) {
  if (type === 'html') {
    return highlightHtmlLine(line);
  }
  let safe = escapeHtml(line);
  if (type === 'css') {
    if (/^\s*\/\*/.test(line)) return `<span class="syn-comment">${safe}</span>`;
    if (line.includes('{')) return `<span class="syn-selector">${safe}</span>`;
    safe = safe.replace(/^(\s*)([-\w]+)(\s*:)/, '$1<span class="syn-property">$2</span>$3');
    return safe.replace(/(:\s*)(.*?)(;?$)/, '$1<span class="syn-value">$2</span>$3');
  }
  safe = safe.replace(/\b(const|let|var|function|return|if|else|forEach|new|true|false|null|async|await)\b/g, '<span class="syn-keyword">$1</span>');
  safe = safe.replace(/(&#039;.*?&#039;|&quot;.*?&quot;|`.*?`)/g, '<span class="syn-string">$1</span>');
  return safe.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="syn-number">$1</span>');
}

const cssMeaning = {
  display:'显示模式。枚举：flex 弹性布局；grid 网格；block 块；none 隐藏',
  position:'定位方式。枚举：relative 相对；absolute 绝对；fixed 视口固定；sticky 吸附',
  background:'背景层，可使用颜色、图片或渐变',
  'background-color':'背景颜色，支持 HEX、rgb()、rgba() 和 CSS 变量',
  color:'前景文字颜色', border:'边框简写：宽度、线型、颜色', 'border-radius':'圆角半径；0 为直角',
  padding:'元素内边距，顺序为上、右、下、左', margin:'元素外边距，顺序为上、右、下、左',
  width:'元素宽度；auto 自动，百分比相对父级', height:'元素高度；auto 由内容决定',
  gap:'Grid/Flex 子项间距', 'grid-template-columns':'网格列定义；fr 为剩余空间比例',
  'align-items':'交叉轴对齐。枚举：start 起点；center 居中；end 末端；stretch 拉伸',
  'justify-content':'主轴分布。枚举：start；center；end；space-between 两端对齐',
  'font-size':'字号大小', 'font-weight':'字重；400 常规，600 半粗，700 粗体',
  overflow:'溢出策略。枚举：visible 显示；hidden 裁切；auto 按需滚动',
  transition:'状态变化的动画时长与缓动', cursor:'鼠标形态；pointer 表示可点击',
  transform:'元素变换：位移、缩放或旋转', 'box-shadow':'元素阴影：X、Y、模糊、扩散、颜色'
};

function annotateLine(line, type) {
  const value = line.trim();
  if (!value) return '空行：分隔相邻代码结构';
  if (type === 'html') {
    if (/^<\//.test(value)) return `结束 ${value.match(/^<\/([\w-]+)/)?.[1] || '当前'} 元素的内容范围`;
    const tag = value.match(/^<([\w-]+)/)?.[1];
    const meanings = {div:'通用容器，用于布局分组',section:'语义区块，表示独立内容区域',header:'区块头部',footer:'区块底部操作区',button:'可点击命令；type 可为 button、submit、reset',input:'输入控件；type 枚举含 text、checkbox、range、color',label:'表单标签，扩大关联控件点击范围',span:'行内容器，用于短文本或状态',table:'表格数据容器',thead:'表头分组',tbody:'表格主体',tr:'表格行',th:'表头单元格',td:'数据单元格',img:'图片资源；alt 提供替代文本',article:'可独立复用的内容条目'};
    return tag ? `${meanings[tag] || `声明 ${tag} 元素`}${/class=/.test(value) ? '；class 用于复用样式' : ''}` : '文本内容：直接显示给用户';
  }
  if (type === 'css') {
    if (value.startsWith('/*')) return 'CSS 注释：说明下一组规则的用途';
    if (value.endsWith('{')) return value.startsWith('@media') ? '响应式条件：仅在指定视口范围内应用内部规则' : `选择器 ${value.slice(0,-1).trim()}：限定后续样式作用范围`;
    if (value === '}') return '结束当前 CSS 规则块';
    const property = value.match(/^([\w-]+)\s*:/)?.[1];
    return property ? (cssMeaning[property] || `${property}：设置该 CSS 属性；值可使用关键字、长度或变量`) : 'CSS 规则续行：与上一行共同定义选择器或属性值';
  }
  if (/^(const|let|var)\s/.test(value)) return '声明变量。const 不可重新赋值；let 可重新赋值；var 为旧式函数作用域';
  if (/addEventListener/.test(value)) return '注册事件监听。常用枚举：click 点击；input 输入；change 提交变更；keydown 键盘按下';
  if (/querySelectorAll/.test(value)) return '按 CSS 选择器获取全部匹配元素，返回 NodeList';
  if (/querySelector/.test(value)) return '按 CSS 选择器获取第一个匹配元素';
  if (/forEach/.test(value)) return '遍历集合，对每个元素执行回调';
  if (/=>\s*{?/.test(value)) return '箭头函数：定义当前事件或遍历的回调逻辑';
  if (value === '});' || value === '}' || value === '};') return '结束当前函数、对象或控制块';
  if (/classList/.test(value)) return '操作元素类名；add 添加、remove 移除、toggle 切换、contains 判断';
  return '执行 JavaScript 语句；具体值由当前组件状态决定';
}

function syncCodeEditor() {
  const editor = document.getElementById('codeEditor');
  editor.value = state.editor[state.activeCode];
  updateEditorMeta();
}

function updateEditorMeta() {
  ['html','css','js'].forEach(type => document.getElementById(`${type}Lines`).textContent = `${state.editor[type].split('\n').length}`);
  const editor=document.getElementById('codeEditor');
  const lines = editor.value.split('\n');
  document.getElementById('lineNumbers').innerHTML = lines.map((_,i)=>`<span class="line-number" data-line="${i}">${i+1}</span>`).join('');
  document.getElementById('codeHighlight').innerHTML = highlightCode(editor.value, state.activeCode);
  document.getElementById('lineComments').innerHTML = lines.map((line,index) => `<div class="line-comment" data-line="${index}" title="${escapeHtml(annotateLine(line,state.activeCode))}"><b>${index+1}</b>${escapeHtml(annotateLine(line,state.activeCode))}</div>`).join('');
  const before=editor.value.slice(0,editor.selectionStart).split('\n');
  document.getElementById('cursorStatus').textContent=`Ln ${before.length}, Col ${before.at(-1).length+1}`;
}

function setLineHover(line, notifyPreview = true) {
  document.querySelectorAll('[data-line].is-hover').forEach(item => item.classList.remove('is-hover'));
  if (line !== null && line !== undefined) {
    document.querySelectorAll(`[data-line="${line}"]`).forEach(item => item.classList.add('is-hover'));
  }
  if (notifyPreview) {
    const frame = document.getElementById('editorPreview');
    frame?.contentWindow?.postMessage({source:'restyle-editor', type:'line-hover', line: state.activeCode === 'html' ? line : null}, '*');
  }
}

function syncLineHover(event) {
  const row = event.target.closest('[data-line]');
  if (!row || !event.currentTarget.contains(row)) return;
  if (event.type === 'mouseout' && event.relatedTarget && row.contains(event.relatedTarget)) return;
  setLineHover(event.type === 'mouseout' ? null : row.dataset.line);
}

let previewTimer;
function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer=setTimeout(()=>{document.getElementById('editorPreview').srcdoc=previewDocument(state.editor);},120);
}

function applyPreviewZoom() {
  const frame = document.getElementById('editorPreview');
  const label = document.getElementById('previewZoomLabel');
  if (!frame || !label) return;
  frame.style.transform = `scale(${state.previewZoom})`;
  frame.style.transformOrigin = 'top center';
  label.textContent = `${Math.round(state.previewZoom * 100)}%`;
}

async function saveEditor() {
  const path=document.getElementById('editorPath').value.trim().replace(/^\/+/, '');
  if(!path || path.endsWith('/')) return toast('请输入包含文件名的项目路径');
  const record={name:document.getElementById('editorTitle').value.trim()||'未命名组件',type:document.getElementById('editorType').textContent,html:state.editor.html,css:state.editor.css,js:state.editor.js,updatedAt:new Date().toISOString()};
  const button = document.getElementById('saveEditor');
  button.disabled = true;
  try {
    const response = await fetch('/api/save', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({path, ...record})
    });
    const result = await response.json().catch(()=>({error:'本地保存服务未返回有效数据'}));
    if (!response.ok || !result.ok) throw new Error(result.error || `保存失败：HTTP ${response.status}`);
    state.saved[path]={...record,files:result.files};
    localStorage.setItem('livemngsys-wss-tree',JSON.stringify(state.saved));
    document.getElementById('treeCount').textContent=Object.keys(state.saved).length;
    toast(`已写入 ReStyle/${result.files[0]}`);
  } catch (error) {
    toast(location.protocol === 'file:' ? '请通过 Start-ReStyle.bat 启动后再保存' : error.message);
  } finally {
    button.disabled = false;
  }
}

function copyTokens() {
  const css = projectTokenCss();
  navigator.clipboard?.writeText(css).then(()=>toast('设计令牌 CSS 已复制')).catch(()=>toast('浏览器未授权剪贴板，请在 HTTPS 或本地服务中重试'));
}

function exportTree() {
  const blob=new Blob([JSON.stringify(state.saved,null,2)],{type:'application/json'});
  const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download='livemngsys-wss-components.json'; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  toast('项目树已导出');
}

function toast(message) { const node=document.createElement('div'); node.className='toast'; node.textContent=message; document.getElementById('toastRegion').append(node); setTimeout(()=>node.remove(),2800); }

function clamp(value, minimum, maximum) { return Math.min(Math.max(value, minimum), maximum); }

function installDragResizer(handle, move, keyboardMove) {
  handle.addEventListener('pointerdown', event => {
    event.preventDefault();
    handle.setPointerCapture?.(event.pointerId);
    handle.classList.add('dragging');
    document.body.classList.add('resizing');
    const onPointerMove = move(event);
    const update = currentEvent => onPointerMove(currentEvent);
    const finish = () => {
      handle.classList.remove('dragging');
      document.body.classList.remove('resizing');
      handle.removeEventListener('pointermove', update);
      handle.removeEventListener('pointerup', finish);
      handle.removeEventListener('pointercancel', finish);
    };
    handle.addEventListener('pointermove', update);
    handle.addEventListener('pointerup', finish);
    handle.addEventListener('pointercancel', finish);
  });
  handle.addEventListener('keydown', event => {
    const delta = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -16 : event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 16 : 0;
    if (!delta) return;
    event.preventDefault();
    keyboardMove(delta);
  });
}

const paneResizer = document.getElementById('paneResizer');
const editorBody = document.querySelector('.editor-body');
installDragResizer(paneResizer, startEvent => event => {
  const rect = editorBody.getBoundingClientRect();
  if (window.innerWidth <= 760) {
    const top = clamp(event.clientY - rect.top, 230, rect.height - 230);
    editorBody.style.gridTemplateRows = `${top}px 8px minmax(230px, 1fr)`;
  } else {
    const left = clamp(event.clientX - rect.left, 320, rect.width - 360);
    editorBody.style.gridTemplateColumns = `${left}px 8px minmax(280px, 1fr)`;
  }
}, delta => {
  const rect = editorBody.getBoundingClientRect();
  if (window.innerWidth <= 760) {
    const current = parseFloat(getComputedStyle(editorBody).gridTemplateRows.split(' ')[0]);
    editorBody.style.gridTemplateRows = `${clamp(current + delta, 230, rect.height - 230)}px 8px minmax(230px, 1fr)`;
  } else {
    const current = parseFloat(getComputedStyle(editorBody).gridTemplateColumns.split(' ')[0]);
    editorBody.style.gridTemplateColumns = `${clamp(current + delta, 320, rect.width - 360)}px 8px minmax(280px, 1fr)`;
  }
});

const commentsResizer = document.getElementById('commentsResizer');
const codeArea = document.querySelector('.code-area-wrap');
installDragResizer(commentsResizer, startEvent => event => {
  if (window.innerWidth <= 760) return;
  const rect = codeArea.getBoundingClientRect();
  const width = clamp(rect.right - event.clientX, 180, rect.width - 272);
  codeArea.style.gridTemplateColumns = `44px minmax(220px, 1fr) 8px ${width}px`;
}, delta => {
  if (window.innerWidth <= 760) return;
  const rect = codeArea.getBoundingClientRect();
  const current = parseFloat(getComputedStyle(codeArea).gridTemplateColumns.split(' ').at(-1));
  const width = clamp(current - delta, 180, rect.width - 272);
  codeArea.style.gridTemplateColumns = `44px minmax(220px, 1fr) 8px ${width}px`;
});

document.querySelectorAll('.nav-item').forEach(item => item.onclick = () => navigate(item.dataset.view));
document.getElementById('menuBtn').onclick=()=>document.getElementById('sidebar').classList.add('open');
document.getElementById('sidebarClose').onclick=()=>document.getElementById('sidebar').classList.remove('open');
document.getElementById('themeButton').onclick=()=>{document.body.classList.toggle('dark');localStorage.setItem('livemngsys-wss-dark',document.body.classList.contains('dark')?'1':'0');};
document.getElementById('newComponentBtn').onclick=()=>{ const id=`custom-${Date.now()}`; samples[id]={name:'新组件',type:'自定义组件',group:'自定义组件',path:'components/custom/new-component.html',description:'',html:'<div class="component">新组件</div>',css:`${previewBase}.component{padding:16px;border:1px solid #dfe5e3;border-radius:7px}`,js:''}; openEditor(id); };
document.getElementById('editorClose').onclick=closeEditor;
document.getElementById('resetEditor').onclick=()=>{state.editor={...state.originals};syncCodeEditor();refreshPreview();toast('已恢复打开时的代码');};
document.getElementById('formatEditor').onclick=()=>{state.editor[state.activeCode]=formatCode(state.editor[state.activeCode],state.activeCode);syncCodeEditor();refreshPreview();toast(`${state.activeCode.toUpperCase()} 已格式化并重新分行`);};
document.getElementById('saveEditor').onclick=saveEditor;
document.getElementById('globalSearch').addEventListener('input',event=>{state.query=event.target.value;if(state.view!=='components')state.view='components';render();});
document.getElementById('globalSearch').addEventListener('keydown',event=>{if(event.key==='Escape'){event.target.value='';state.query='';render();}});
document.querySelectorAll('.code-tabs button').forEach(button=>button.onclick=()=>{state.activeCode=button.dataset.code;document.querySelectorAll('.code-tabs button').forEach(b=>b.classList.toggle('active',b===button));syncCodeEditor();});
document.getElementById('codeEditor').addEventListener('input',event=>{state.editor[state.activeCode]=event.target.value;updateEditorMeta();refreshPreview();});
document.getElementById('codeEditor').addEventListener('click',updateEditorMeta);
document.getElementById('codeEditor').addEventListener('keyup',updateEditorMeta);
document.getElementById('codeEditor').addEventListener('scroll',event=>{
  document.getElementById('lineNumbers').scrollTop=event.target.scrollTop;
  document.getElementById('codeHighlight').scrollTop=event.target.scrollTop;
  document.getElementById('codeHighlight').scrollLeft=event.target.scrollLeft;
  document.getElementById('lineComments').scrollTop=event.target.scrollTop;
});
document.getElementById('codeEditor').addEventListener('mousemove',event=>{
  const editor = event.currentTarget;
  const offset = event.clientY - editor.getBoundingClientRect().top + editor.scrollTop - 14;
  const line = Math.floor(offset / 23.1);
  setLineHover(line >= 0 && line < editor.value.split('\n').length ? line : null);
});
document.getElementById('codeEditor').addEventListener('mouseleave',()=>setLineHover(null));
document.getElementById('lineComments').addEventListener('mouseover',syncLineHover);
document.getElementById('lineComments').addEventListener('mouseout',syncLineHover);
window.addEventListener('message', event => {
  const data = event.data;
  if (!data || data.source !== 'restyle-preview' || data.type !== 'element-hover') return;
  setLineHover(data.line, false);
});
document.getElementById('codeEditor').addEventListener('keydown',event=>{if(event.key==='Tab'){event.preventDefault();const e=event.target,start=e.selectionStart,end=e.selectionEnd;e.setRangeText('  ',start,end,'end');e.dispatchEvent(new Event('input'));}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveEditor();}});
document.querySelectorAll('.viewport-switch button').forEach(button=>button.onclick=()=>{document.querySelectorAll('.viewport-switch button').forEach(b=>b.classList.toggle('active',b===button));const width=button.dataset.width;document.getElementById('editorPreview').style.width=width;document.getElementById('previewSize').textContent=width==='100%'?'自适应':width;});
document.getElementById('previewZoomOut').onclick=()=>{state.previewZoom=Math.max(.6,Number((state.previewZoom-.1).toFixed(2)));applyPreviewZoom();};
document.getElementById('previewZoomIn').onclick=()=>{state.previewZoom=Math.min(1.8,Number((state.previewZoom+.1).toFixed(2)));applyPreviewZoom();};
document.getElementById('previewZoomReset').onclick=()=>{state.previewZoom=1;applyPreviewZoom();};
document.getElementById('openPreview').onclick=()=>{const win=window.open('','_blank');if(win){win.document.open();win.document.write(previewDocument(state.editor));win.document.close();}};
document.addEventListener('keydown',event=>{if(event.key==='/'&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)){event.preventDefault();document.getElementById('globalSearch').focus();}if(event.key==='Escape'&&document.getElementById('editorLayer').classList.contains('open'))closeEditor();});
window.addEventListener('hashchange',()=>{const view=location.hash.slice(1);if(titleMap[view]){state.view=view;render();}});
window.addEventListener('load',iconRefresh);

if(localStorage.getItem('livemngsys-wss-dark')==='1')document.body.classList.add('dark');
document.getElementById('treeCount').textContent=Object.keys(state.saved).length;
const initial=location.hash.slice(1); if(titleMap[initial])state.view=initial;
render();
