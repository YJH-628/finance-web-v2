<script setup>
import { ref, computed, watch, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { Chart, registerables } from 'chart.js'
import { Wallet, LayoutDashboard, ArrowLeftRight, Tags, Sparkles, Plus, ArrowUpRight, ArrowDownLeft, Download, Upload, Search, ChevronRight, X, Trash2, Send, Menu, RefreshCw, Database, TrendingUp, ShieldCheck, CircleHelp } from '@lucide/vue'

Chart.register(...registerables)
const page = ref('overview'), records = ref([]), categories = ref([]), loading = ref(true)
const search = ref(''), typeFilter = ref('全部'), month = ref(''), modal = ref(false), mobileNav = ref(false)
const busy = ref(false), notice = ref(''), error = ref(''), fileInput = ref(null)
const today = () => new Date().toLocaleDateString('en-CA')
const form = ref({ date: today(), type: '支出', category: '', amount: '', description: '' })
const categoryForm = ref({ name: '', type: '支出', color: '#219b80' })
const tabs = [{ id: 'overview', label: '财务总览', icon: LayoutDashboard }, { id: 'records', label: '收支明细', icon: ArrowLeftRight }, { id: 'categories', label: '分类管理', icon: Tags }, { id: 'ai', label: 'AI 理财助手', icon: Sparkles }]
const title = computed(() => tabs.find(t => t.id === page.value)?.label)
const availableCategories = computed(() => categories.value.filter(c => c.type === form.value.type))
watch(availableCategories, cats => { if (!cats.some(c => c.name === form.value.category)) form.value.category = cats[0]?.name || '' })
const months = computed(() => [...new Set(records.value.map(r => r.date.slice(0, 7)))].sort().reverse())
const selectedRecords = computed(() => records.value.filter(r => !month.value || r.date.startsWith(month.value)))
const income = computed(() => selectedRecords.value.filter(r => r.type === '收入').reduce((a, r) => a + r.amount, 0))
const expense = computed(() => selectedRecords.value.filter(r => r.type === '支出').reduce((a, r) => a + r.amount, 0))
const balance = computed(() => income.value - expense.value)
const saving = computed(() => income.value ? Math.round(balance.value / income.value * 100) : 0)
const filtered = computed(() => selectedRecords.value.filter(r => (typeFilter.value === '全部' || r.type === typeFilter.value) && `${r.category} ${r.description} ${r.date}`.toLowerCase().includes(search.value.toLowerCase())))
const tablePage = ref(1), pageSize = 10
watch([search, typeFilter, month], () => { tablePage.value = 1 })
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
watch(pageCount, n => { tablePage.value = Math.min(tablePage.value, n) })
const displayed = computed(() => page.value === 'overview' ? filtered.value.slice(0, 5) : filtered.value.slice((tablePage.value - 1) * pageSize, tablePage.value * pageSize))
const money = n => Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const color = name => categories.value.find(c => c.name === name)?.color || '#8a9b96'
const breakdown = computed(() => {
  const result = {}
  selectedRecords.value.filter(r => r.type === '支出').forEach(r => { result[r.category] = (result[r.category] || 0) + r.amount })
  return Object.entries(result).map(([name, value]) => ({ name, value, color: color(name), percent: expense.value ? Math.round(value / expense.value * 100) : 0 })).sort((a, b) => b.value - a.value)
})
let timer
function toast(text) { notice.value = text; clearTimeout(timer); timer = setTimeout(() => { notice.value = '' }, 4000) }
async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' } })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || '请求失败，请稍后重试')
  return data
}
async function load() {
  error.value = ''
  try { [records.value, categories.value] = await Promise.all([api('/api/records'), api('/api/categories')]) }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}
async function action(fn) { if (busy.value) return; busy.value = true; try { await fn() } catch (e) { toast(e.message) } finally { busy.value = false } }
function openRecord() { form.value = { date: today(), type: '支出', category: categories.value.find(c => c.type === '支出')?.name || '', amount: '', description: '' }; modal.value = true }
function addRecord() { action(async () => { await api('/api/records', { method: 'POST', body: JSON.stringify(form.value) }); modal.value = false; await load(); toast('记账成功，每一笔都值得被记录') }) }
function deleteRecord(r) { if (confirm(`确定删除「${r.category} ¥${money(r.amount)}」？`)) action(async () => { await api(`/api/records/${r.id}`, { method: 'DELETE' }); await load(); toast('记录已删除') }) }
function dataset(kind) { if (confirm(kind === 'clear' ? '确定清空 V2 的全部收支记录？此操作无法撤销。' : '向 V2 账本添加演示数据？')) action(async () => { const d = await api(`/api/records/${kind}`, { method: 'POST' }); await load(); toast(kind === 'clear' ? 'V2 记录已清空' : `已添加 ${d.count} 条记录`) }) }
function importCsv(event) { const file = event.target.files[0]; if (!file) return; action(async () => { const body = new FormData(); body.append('file', file); const d = await api('/api/import', { method: 'POST', body }); await load(); toast(`已导入 ${d.count} 条记录`) }); event.target.value = '' }
function addCategory() { action(async () => { await api('/api/categories', { method: 'POST', body: JSON.stringify(categoryForm.value) }); categoryForm.value.name = ''; await load(); toast('分类已添加') }) }
function deleteCategory(c) { if (confirm(`删除分类「${c.name}」？已有记录将保留。`)) action(async () => { await api(`/api/categories/${c.id}`, { method: 'DELETE' }); await load(); toast('分类已删除') }) }
const trendCanvas = ref(null), donutCanvas = ref(null)
let trend, donut
async function renderCharts() {
  await nextTick(); trend?.destroy(); donut?.destroy(); trend = null; donut = null
  if (page.value !== 'overview' || !trendCanvas.value) return
  const daily = {}
  selectedRecords.value.forEach(r => { const key = r.date; daily[key] ||= { income: 0, expense: 0 }; daily[key][r.type === '收入' ? 'income' : 'expense'] += r.amount })
  const days = Object.keys(daily).sort()
  trend = new Chart(trendCanvas.value, { type: 'line', data: { labels: days.map(d => d.slice(5)), datasets: [
    { label: '收入', data: days.map(d => daily[d].income), borderColor: '#219b80', backgroundColor: '#219b8014', fill: true, tension: .35, pointRadius: days.length > 25 ? 0 : 3, borderWidth: 2 },
    { label: '支出', data: days.map(d => daily[d].expense), borderColor: '#e1a367', backgroundColor: '#e1a36708', fill: true, tension: .35, pointRadius: days.length > 25 ? 0 : 3, borderWidth: 2 },
  ] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 7, color: '#96a19b' }, border: { display: false } }, y: { grid: { color: '#f0f3f1' }, border: { display: false }, ticks: { color: '#96a19b', callback: n => n >= 1000 ? `${n / 1000}k` : n } } } } })
  donut = new Chart(donutCanvas.value, { type: 'doughnut', data: { labels: breakdown.value.map(c => c.name), datasets: [{ data: breakdown.value.length ? breakdown.value.map(c => c.value) : [1], backgroundColor: breakdown.value.length ? breakdown.value.map(c => c.color) : ['#edf2ef'], borderWidth: 4, borderColor: '#fff', borderRadius: 5 }] }, options: { cutout: '78%', maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: !!breakdown.value.length } } } })
}
watch([page, selectedRecords, categories], renderCharts)
onMounted(async () => { await load(); await renderCharts() })
const advice = ref(''), analyzing = ref(false), messages = ref([]), question = ref(''), chatting = ref(false), chatBox = ref(null)
async function analyze() { analyzing.value = true; try { advice.value = (await api('/api/ai/advice', { method: 'POST', body: '{}' })).advice } catch (e) { toast(e.message) } finally { analyzing.value = false } }
async function sendQuestion(value) {
  const text = (value || question.value).trim(); if (!text || chatting.value) return
  const history = messages.value.filter(m => m.content).map(m => ({ ...m })).slice(-10)
  messages.value.push({ role: 'user', content: text }, { role: 'assistant', content: '' }); const reply = messages.value[messages.value.length - 1]
  question.value = ''; chatting.value = true
  try {
    const response = await fetch('/api/ai/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, history }) })
    if (!response.ok) throw new Error((await response.json()).error || 'AI 服务暂时不可用')
    const reader = response.body.getReader(), decoder = new TextDecoder(); let pending = ''
    while (true) {
      const { value, done } = await reader.read(); pending += decoder.decode(value, { stream: !done })
      const lines = pending.split('\n'); pending = lines.pop()
      for (const line of lines) { if (!line.startsWith('data: ')) continue; const content = line.slice(6).trim(); if (content === '[DONE]') continue; const data = JSON.parse(content); if (data.error) throw new Error(data.error); reply.content += data.content || '' }
      await nextTick(); if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
      if (done) break
    }
  } catch (e) { if (!reply.content) reply.content = e.message } finally { chatting.value = false }
}
onBeforeUnmount(() => { trend?.destroy(); donut?.destroy(); clearTimeout(timer) })
</script>

<template>
  <div class="shell">
    <aside :class="['sidebar', { open: mobileNav }]">
      <a class="brand" href="#" @click.prevent="page = 'overview'"><span class="brand-icon"><Wallet :size="24" /></span>Finance<span class="brand-ai">AI</span><small>V2</small></a>
      <div class="workspace"><span class="avatar">L</span><div><strong>我的个人账本</strong><small>PERSONAL WORKSPACE</small></div><ChevronRight :size="15" /></div>
      <p class="nav-label">工作空间</p>
      <nav><button v-for="tab in tabs" :key="tab.id" :class="{ active: page === tab.id }" @click="page = tab.id; mobileNav = false"><component :is="tab.icon" :size="19" />{{ tab.label }}<span v-if="tab.id === 'ai'" class="nav-badge">AI</span></button></nav>
      <div class="sidebar-bottom"><div class="side-tip"><span class="tip-symbol">✦</span><strong>小习惯，大改变</strong><p>从记录每一笔开始，<br>让理想生活有迹可循。</p><span>让每一笔，都更有数 <ArrowUpRight :size="14" /></span></div><div class="privacy"><ShieldCheck :size="16" />本地存储 · 独立账本</div><div class="profile"><span class="avatar light">我</span><div><strong>个人账户</strong><small>FinanceAI Personal</small></div><CircleHelp :size="18" /></div></div>
    </aside>
    <div v-if="mobileNav" class="nav-overlay" @click="mobileNav = false"></div>
    <main>
      <header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileNav = !mobileNav"><Menu :size="21" /></button><span>我的工作空间</span><ChevronRight :size="14" /><strong>{{ title }}</strong></div><div class="top-right"><span class="live-dot"></span> 本地账本 <span class="top-divider"></span><span class="avatar small">我</span></div></header>
      <div class="content">
        <section class="page-heading"><div><p class="eyebrow">YOUR MONEY, YOUR LIFE</p><h1>{{ page === 'overview' ? '掌握财务，生活更从容' : title }}<span v-if="page === 'overview'" class="heading-spark">✳</span></h1><p>{{ page === 'overview' ? '每一笔收支，都是通往理想生活的一小步。' : page === 'records' ? '认真记录，让每一笔收支清晰可见。' : page === 'categories' ? '有条理的分类，让你的财务一目了然。' : '把复杂的数字，变成简单可行的下一步。' }}</p></div><div class="heading-actions"><select v-model="month" aria-label="选择统计月份"><option value="">全部时间</option><option v-for="m in months" :key="m">{{ m }}</option></select><button class="button primary" @click="openRecord"><Plus :size="17" />记一笔</button></div></section>
        <div v-if="error" class="error-banner">{{ error }}<button @click="load">重新加载</button></div>
        <div v-if="loading" class="loading-state"><RefreshCw class="spin" /> 正在同步你的账本…</div>

        <template v-if="page === 'overview'">
          <div class="stats-grid">
            <article class="stat balance"><div class="stat-top"><span>净结余</span><Wallet :size="18" /></div><div class="stat-number"><small>¥</small>{{ money(balance) }}</div><div class="stat-foot"><span class="pill">{{ saving }}%</span> 收入结余率<span class="decorative-ring"></span></div></article>
            <article class="stat"><div class="stat-top"><span>总收入</span><span class="stat-icon green"><ArrowDownLeft :size="19" /></span></div><div class="stat-number"><small>¥</small>{{ money(income) }}</div><div class="stat-foot"><span class="mini-dot green-bg"></span>{{ selectedRecords.filter(r => r.type === '收入').length }} 笔收入记录</div></article>
            <article class="stat"><div class="stat-top"><span>总支出</span><span class="stat-icon orange"><ArrowUpRight :size="19" /></span></div><div class="stat-number"><small>¥</small>{{ money(expense) }}</div><div class="stat-foot"><span class="mini-dot orange-bg"></span>{{ selectedRecords.filter(r => r.type === '支出').length }} 笔支出记录</div></article>
            <article class="stat"><div class="stat-top"><span>收支记录</span><span class="stat-icon blue"><ArrowLeftRight :size="18" /></span></div><div class="stat-number">{{ selectedRecords.length }}<small class="unit">笔</small></div><div class="stat-foot">一点一滴，记录生活的轨迹</div></article>
          </div>
          <div class="chart-grid"><section class="panel trend-panel"><div class="panel-heading"><div><h2>收支趋势</h2><p>看见每一段时间里的财务变化</p></div><div class="legend"><span><i class="green-bg"></i>收入</span><span><i class="orange-bg"></i>支出</span></div></div><div class="trend-chart"><canvas ref="trendCanvas"></canvas><div v-if="!selectedRecords.length" class="chart-empty">记下第一笔，开启你的财务旅程</div></div></section>
          <section class="panel"><div class="panel-heading"><div><h2>支出去向</h2><p>把钱花在真正重要的地方</p></div><Tags :size="18" class="muted" /></div><div class="donut-area"><canvas ref="donutCanvas"></canvas><div class="donut-center"><small>总支出</small><strong>¥{{ money(expense) }}</strong></div></div><div class="category-legend"><div v-for="c in breakdown.slice(0, 4)" :key="c.name"><span><i :style="{ background: c.color }"></i>{{ c.name }}</span><strong>{{ c.percent }}<small>%</small></strong></div><p v-if="!breakdown.length" class="empty-small">暂无支出数据</p></div></section></div>
          <div class="insight-banner"><span class="insight-icon"><Sparkles :size="23" /></span><div><strong>你的财务，值得一个聪明的伙伴</strong><p>让 AI 读懂收支背后的故事，为你找到更好的理财方式。</p></div><button class="button" @click="page = 'ai'">获取专属建议<ArrowUpRight :size="16" /></button></div>
        </template>

        <section v-if="page === 'overview' || page === 'records'" class="panel records-panel"><div class="panel-heading"><div><h2>{{ page === 'overview' ? '最近收支' : '全部收支记录' }} <span class="count-badge">{{ filtered.length }}</span></h2><p>{{ page === 'overview' ? '生活的每一笔，都有迹可循' : '支持按月份、类型、分类或备注查找' }}</p></div><button v-if="page === 'overview'" class="text-button" @click="page = 'records'">查看全部<ChevronRight :size="15" /></button><div v-else class="table-actions"><button class="button" :disabled="busy" @click="fileInput.click()"><Upload :size="15" />导入</button><a class="button" href="/api/export"><Download :size="15" />导出</a></div></div>
          <div class="table-toolbar"><div class="segmented"><button v-for="t in ['全部', '支出', '收入']" :key="t" :class="{ selected: typeFilter === t }" @click="typeFilter = t">{{ t }}</button></div><label class="search"><Search :size="16" /><input v-model="search" placeholder="搜索分类、备注…" aria-label="搜索收支记录" /></label></div>
          <div class="table-scroll"><table><thead><tr><th>交易 / 分类</th><th>日期</th><th>类型</th><th>备注</th><th class="amount-cell">金额</th><th></th></tr></thead><tbody><tr v-for="r in displayed" :key="r.id"><td><div class="category-cell"><span class="category-icon" :style="{ color: color(r.category), background: color(r.category) + '14' }"><Tags :size="17" /></span><strong>{{ r.category }}</strong></div></td><td class="muted">{{ r.date }}</td><td><span :class="['type-tag', { incoming: r.type === '收入' }]">{{ r.type }}</span></td><td class="description-cell">{{ r.description || '—' }}</td><td :class="['amount-cell', 'record-amount', { positive: r.type === '收入' }]">{{ r.type === '收入' ? '+' : '−' }} ¥{{ money(r.amount) }}</td><td><button class="icon-button delete-button" :disabled="busy" aria-label="删除记录" @click="deleteRecord(r)"><Trash2 :size="15" /></button></td></tr><tr v-if="!displayed.length"><td colspan="6" class="empty-state"><Wallet :size="30" /><strong>{{ records.length ? '没有找到匹配的记录' : '你的账本，从第一笔开始' }}</strong><p>{{ records.length ? '试试调整筛选条件' : '点击「记一笔」，或导入演示数据体验' }}</p><button v-if="!records.length" class="button" :disabled="busy" @click="dataset('seed')">导入演示数据</button></td></tr></tbody></table></div>
          <div class="table-footer"><span>共 {{ filtered.length }} 条记录{{ page === 'overview' ? ' · 显示最近 5 条' : '' }}</span><div v-if="page === 'records'" class="pagination"><button :disabled="tablePage === 1" @click="tablePage--">上一页</button><span>{{ tablePage }} / {{ pageCount }}</span><button :disabled="tablePage >= pageCount" @click="tablePage++">下一页</button></div><span v-else class="secure-label"><ShieldCheck :size="13" />数据仅存储在本地</span></div>
        </section>
        <section v-if="page === 'records'" class="panel tools-panel"><div><Database :size="19" /><div><strong>账本工具</strong><p>以下操作仅作用于独立的 V2 账本</p></div></div><div class="table-actions"><button class="button" :disabled="busy" @click="dataset('seed')">演示数据</button><button class="button" :disabled="busy" @click="dataset('random')">随机生成</button><button class="button danger" :disabled="busy" @click="dataset('clear')">清空账本</button></div></section>

        <template v-if="page === 'categories'"><section class="panel"><div class="panel-heading"><div><h2>新增分类</h2><p>为不同的生活场景，找到合适的位置</p></div></div><form class="category-form" @submit.prevent="addCategory"><input v-model="categoryForm.name" required maxlength="30" placeholder="分类名称，如：旅行" aria-label="分类名称" /><select v-model="categoryForm.type" aria-label="分类类型"><option>支出</option><option>收入</option></select><input v-model="categoryForm.color" type="color" aria-label="分类颜色" /><button class="button primary" :disabled="busy"><Plus :size="16" />新增分类</button></form></section><section v-for="type in ['支出', '收入']" :key="type" class="panel"><div class="panel-heading"><div><h2>{{ type }}分类</h2><p>删除分类不会影响已记录的历史账目</p></div></div><div class="category-grid"><div v-for="c in categories.filter(c => c.type === type)" :key="c.id" class="category-card"><span class="category-icon" :style="{ color: c.color, background: c.color + '14' }"><Tags :size="21" /></span><strong>{{ c.name }}</strong><button class="icon-button" :disabled="busy" aria-label="删除分类" @click="deleteCategory(c)"><Trash2 :size="15" /></button></div></div></section></template>

        <div v-if="page === 'ai'" class="ai-grid"><section class="panel advice-panel"><span class="ai-symbol"><Sparkles :size="27" /></span><p class="eyebrow">FINANCIAL INTELLIGENCE</p><h2>一份更懂你的财务诊断</h2><p class="muted">结合全部账本数据，分析消费结构、储蓄习惯，给出可执行的建议。</p><button class="button primary" :disabled="analyzing" @click="analyze"><RefreshCw v-if="analyzing" :size="16" class="spin" /><Sparkles v-else :size="16" />{{ analyzing ? '正在分析你的账本…' : advice ? '重新分析' : '生成专属财务报告' }}</button><div v-if="advice" class="advice-text">{{ advice }}</div><div v-else class="advice-placeholder"><TrendingUp :size="36" /><p>让数字开口，让行动有方向</p></div><small class="ai-note">AI 分析会将账本摘要发送至已配置的 DeepSeek 服务，仅供参考。</small></section><section class="panel chat-panel"><div class="panel-heading"><div><h2><span class="live-dot"></span> 财务问答助手</h2><p>关于你的钱，随时聊一聊</p></div><span class="count-badge">DeepSeek</span></div><div ref="chatBox" class="chat-messages"><div v-if="!messages.length" class="chat-welcome"><Sparkles :size="34" /><h3>你好，今天想了解什么？</h3><p>我可以帮你分析账本、规划储蓄，<br>让理财变得更简单。</p><button v-for="q in ['我的主要支出在哪里？', '如何提高我的储蓄率？', '帮我分析目前的收支情况']" :key="q" @click="sendQuestion(q)">{{ q }}<ArrowUpRight :size="14" /></button></div><div v-for="(m, i) in messages" :key="i" :class="['chat-message', m.role]"><span class="message-avatar">{{ m.role === 'user' ? '我' : '✦' }}</span><div>{{ m.content || '正在思考…' }}</div></div></div><form class="chat-input" @submit.prevent="sendQuestion()"><input v-model="question" :disabled="chatting" placeholder="问问你的 AI 理财助手…" aria-label="输入财务问题" /><button class="button primary" :disabled="chatting || !question.trim()" aria-label="发送问题"><Send :size="17" /></button></form></section></div>
        <footer class="page-footer"><span>FinanceAI <b>V2</b> · 认真生活，从容理财</span><span>Designed for your everyday.</span></footer>
      </div>
    </main>
    <input ref="fileInput" type="file" accept=".csv" hidden @change="importCsv" />
    <div v-if="modal" class="modal-backdrop" @click.self="modal = false"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="record-title"><div class="modal-header"><div><p class="eyebrow">A LITTLE EVERY DAY</p><h2 id="record-title">记下一笔生活</h2></div><button class="icon-button" aria-label="关闭" @click="modal = false"><X :size="21" /></button></div><form @submit.prevent="addRecord"><div class="segmented form-types"><button v-for="t in ['支出', '收入']" :key="t" type="button" :class="{ selected: form.type === t }" @click="form.type = t">{{ t }}</button></div><label class="amount-input">金额（元）<div><span>¥</span><input v-model="form.amount" type="number" min="0.01" step="0.01" required placeholder="0.00" /></div></label><div class="form-row"><label>日期<input v-model="form.date" required type="date" /></label><label>分类<select v-model="form.category" required><option value="" disabled>请选择分类</option><option v-for="c in availableCategories" :key="c.id">{{ c.name }}</option></select></label></div><label>备注<input v-model="form.description" maxlength="250" placeholder="为这笔收支写点什么（选填）" /></label><button class="button primary submit-record" :disabled="busy">{{ busy ? '正在保存…' : '保存这笔记录' }}</button></form></section></div>
    <div v-if="notice" class="toast" role="status"><ShieldCheck :size="18" />{{ notice }}</div>
  </div>
</template>