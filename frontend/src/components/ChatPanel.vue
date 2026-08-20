<template>
  <section class="chat card">
    <div class="chat__head">
      <div>
        <h2 class="chat__title">AI 数据问答</h2>
        <p class="chat__sub">自然语言提问，回答基于数据库实查</p>
      </div>
    </div>

    <div class="chat__body" ref="bodyRef">
      <div v-if="messages.length === 0" class="chat__empty">
        <p>试试问我：</p>
        <ul>
          <li>哪个品类的门店营业额最高？</li>
          <li>牛肉poke 六月卖了多少钱？</li>
          <li>客单价最近是涨了还是跌了？</li>
        </ul>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="chat__msg" :class="`chat__msg--${m.role}`">
        <div class="chat__bubble">
          <span v-if="m.role === 'assistant' && m.querying" class="chat__querying">{{ m.querying }}</span>{{ m.content }}
        </div>
        <details v-if="m.role === 'assistant' && m.tools && m.tools.length" class="chat__sources">
          <summary>查看数据来源（{{ m.tools.length }}）</summary>
          <div v-for="(t, j) in m.tools" :key="j" class="chat__source">
            <div class="chat__source-name">{{ t.tool }} · {{ toolLabel(t.tool) }}</div>
            <div class="chat__source-args">参数：{{ pretty(t.args) }}</div>
            <div class="chat__source-result">结果：{{ pretty(t.result) }}</div>
          </div>
        </details>
      </div>
    </div>

    <form class="chat__input" @submit.prevent="send">
      <input
        v-model="draft"
        placeholder="用自然语言问数据问题…"
        :disabled="loading"
        autocomplete="off"
      />
      <button type="submit" :disabled="loading || !draft.trim()">发送</button>
    </form>
  </section>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const emit = defineEmits(['focus'])

const TOOL_LABELS = {
  get_revenue_summary: '营业额汇总',
  get_store_ranking: '门店排行',
  get_category_ranking: '品类排行',
  get_product_sales: '单品销售',
  get_daily_trend: '每日趋势',
  get_sales_anomalies: '异常销售预警',
}

const messages = ref([])
const draft = ref('')
const loading = ref(false)
const bodyRef = ref(null)

function toolLabel(name) {
  return TOOL_LABELS[name] || name
}

function pretty(v) {
  if (v === null || v === undefined) return '—'
  try {
    return JSON.stringify(v, null, 1)
  } catch {
    return String(v)
  }
}

async function scrollBottom() {
  await nextTick()
  if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  draft.value = ''
  messages.value.push({ role: 'user', content: text })

  const history = messages.value
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(0, -1)
    .map(({ role, content }) => ({ role, content }))

  const assistantMsg = { role: 'assistant', content: '', tools: [], querying: '正在分析…' }
  messages.value.push(assistantMsg)
  loading.value = true
  await scrollBottom()

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
    })
    if (!res.ok || !res.body) {
      throw new Error(res.ok ? '无响应流' : `HTTP ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const raw = buf.slice(0, idx).trim()
        buf = buf.slice(idx + 2)
        if (!raw.startsWith('data:')) continue
        let data
        try {
          data = JSON.parse(raw.slice(5).trim())
        } catch {
          continue
        }
        if (data.type === 'status') {
          assistantMsg.querying = `正在查询「${toolLabel(data.tool)}」…`
        } else if (data.type === 'delta') {
          if (assistantMsg.querying) assistantMsg.querying = ''
          assistantMsg.content += data.content
        } else if (data.type === 'done') {
          assistantMsg.tools = data.tool_calls || []
          if (data.focus) emit('focus', data.focus)
        } else if (data.type === 'error') {
          assistantMsg.content = '出错了：' + data.message
        }
        await scrollBottom()
      }
    }
  } catch (e) {
    assistantMsg.content = assistantMsg.content || ('出错了：' + (e.message || e))
  } finally {
    loading.value = false
    assistantMsg.querying = ''
    await scrollBottom()
  }
}
</script>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 560px;
}
.chat__head {
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border);
}
.chat__title {
  margin: 0 0 2px;
  font-size: 16px;
  font-weight: 700;
}
.chat__sub {
  margin: 0;
  font-size: 12px;
  color: var(--text-2);
}
.chat__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat__empty {
  color: var(--text-2);
  font-size: 13px;
  margin: auto;
  text-align: center;
}
.chat__empty ul {
  margin: 8px 0 0;
  padding-left: 18px;
  text-align: left;
}
.chat__empty li {
  margin: 4px 0;
  color: var(--text);
}
.chat__msg {
  display: flex;
  flex-direction: column;
  max-width: 82%;
}
.chat__msg--user {
  align-self: flex-end;
}
.chat__msg--assistant {
  align-self: flex-start;
}
.chat__bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat__msg--user .chat__bubble {
  background: var(--brand);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.chat__msg--assistant .chat__bubble {
  background: var(--bg-soft, #f4f6f8);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.chat__querying {
  color: var(--text-2);
  display: inline-block;
  margin-right: 6px;
  animation: chat-blink 1.2s infinite;
}
@keyframes chat-blink {
  50% { opacity: 0.4; }
}
.chat__sources {
  margin-top: 6px;
  font-size: 12px;
}
.chat__sources summary {
  cursor: pointer;
  color: var(--brand);
}
.chat__source {
  margin-top: 8px;
  padding: 8px 10px;
  background: #fafbfc;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.chat__source-name {
  font-weight: 600;
  margin-bottom: 4px;
}
.chat__source-args,
.chat__source-result {
  color: var(--text-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
}
.chat__input {
  display: flex;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.chat__input input {
  flex: 1;
  font-family: inherit;
  font-size: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.chat__input button {
  border: none;
  background: var(--brand);
  color: #fff;
  padding: 0 20px;
  font-size: 14px;
  border-radius: 8px;
}
.chat__input button:disabled {
  opacity: 0.5;
}
</style>