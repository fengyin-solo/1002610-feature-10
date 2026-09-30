<template>
  <section class="page" data-module="qualitycheck">
    <header class="page-head">
      <div>
        <h2>质量监察时间轴</h2>
        <p class="page-desc">
          监察记录按 待监察 → 监察中 → 待整改 → 已闭合 四个阶段铺开；
          逾期记录标红并自动退回待整改，节点上留痕谁在什么时间处理。
        </p>
      </div>
      <div class="page-actions">
        <label class="month-picker">
          <span>监察月份</span>
          <input v-model="month" type="month" @change="reload" />
        </label>
        <button class="btn" type="button" @click="month = ''; reload()">全部月份</button>
        <button class="btn primary" type="button" @click="openCreate">登记监察记录</button>
        <button class="btn" type="button" @click="exportRows">导出当月监察清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="item.danger ? 'danger' : ''">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p v-if="message" class="error-text" role="status">{{ message }}</p>

    <div class="timeline-board">
      <section v-for="stage in stages" :key="stage.stage" class="tl-stage">
        <header class="tl-stage-head">
          <span class="tl-dot" :class="stageClass(stage.stage)"></span>
          <h3>{{ stage.stage }}</h3>
          <span class="tl-count">{{ stage.entries.length }}</span>
        </header>

        <div class="tl-cards">
          <article
            v-for="entry in stage.entries"
            :key="String(entry.id)"
            class="tl-card"
            :class="{ overdue: entry.overdue, closed: entry.status === '已闭合' }"
          >
            <div class="tl-card-head">
              <strong>{{ entry['监察编号'] }}</strong>
              <span v-if="entry.overdue" class="badge badge-danger">逾期{{ overdueDays(entry) }}天</span>
              <span v-else-if="entry.status === '待整改'" class="badge">期限 {{ entry['整改期限'] }}</span>
            </div>
            <p class="tl-line"><span class="tl-k">区域</span>{{ entry['监察区域'] }}</p>
            <p class="tl-line"><span class="tl-k">事项</span>{{ entry['监察事项'] }}</p>
            <p v-if="entry['发现违章']" class="tl-line tl-clause-line">
              <span class="tl-k">违章</span>
              <button
                v-if="entry['违章条款']"
                class="link"
                type="button"
                :title="'查看条款 ' + entry['违章条款']"
                @click="openClause(String(entry['违章条款']))"
              >
                {{ entry['发现违章'] }}（{{ entry['违章条款'] }}）
              </button>
              <span v-else>{{ entry['发现违章'] }}</span>
            </p>
            <p v-if="entry['整改要求']" class="tl-line"><span class="tl-k">要求</span>{{ entry['整改要求'] }}</p>
            <p v-if="entry['整改人']" class="tl-line">
              <span class="tl-k">整改</span>{{ entry['整改人'] }} · {{ entry['整改时间'] }}
            </p>

            <ol class="tl-nodes">
              <li v-for="(node, idx) in entry.timeline" :key="idx" :class="{ auto: node.auto }">
                <span class="node-time">{{ node.time }}</span>
                <span class="node-action">{{ node.action }}</span>
                <span class="node-who">{{ node.operator }}</span>
                <span v-if="node.note" class="node-note">{{ node.note }}</span>
              </li>
            </ol>

            <footer class="tl-card-foot">
              <template v-if="entry.status !== '已闭合'">
                <button v-if="entry.status === '待监察'" class="link" type="button" @click="runAction('开展监察', entry)">开展监察</button>
                <button
                  v-if="entry.status === '监察中' || entry.status === '待整改'"
                  class="link"
                  type="button"
                  @click="openIssue(entry)"
                >下达整改</button>
                <button v-if="entry.status === '待整改'" class="link" type="button" @click="openClose(entry)">确认闭合</button>
              </template>
              <span v-else class="closed-tip">已闭合 · 记录锁定</span>
            </footer>
          </article>

          <p v-if="!stage.entries.length" class="tl-empty">暂无记录</p>
        </div>
      </section>
    </div>

    <!-- 登记监察记录 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记监察记录</h3>
        <p class="modal-tip">同一区域、同一天只允许开一条单，重复单会被时间轴挡下。</p>
        <label v-for="f in createForm" :key="f.key" class="form-row">
          <span>{{ f.label }}<i v-if="f.required">*</i></span>
          <input v-model="createValues[f.key]" :placeholder="f.placeholder" />
        </label>
        <label class="form-row">
          <span>违章条款</span>
          <select v-model="createValues['违章条款']">
            <option value="">无违章（待监察阶段可不选）</option>
            <option v-for="c in clauses" :key="c.code" :value="c.code">
              {{ c.code }} · {{ c.category }}
            </option>
          </select>
        </label>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </footer>
      </form>
    </div>

    <!-- 下达整改 -->
    <div v-if="issuing" class="modal-mask" @click.self="issuing = false">
      <form class="modal" @submit.prevent="submitIssue">
        <h3>下达整改 · {{ issuingEntry?.['监察编号'] }}</h3>
        <p class="modal-tip">整改要求、整改期限与违章条款都填写后才能下达。</p>
        <label class="form-row">
          <span>发现违章<i>*</i></span>
          <textarea v-model="issueValues['发现违章']" rows="2"></textarea>
        </label>
        <label class="form-row">
          <span>违章条款<i>*</i></span>
          <select v-model="issueValues['违章条款']">
            <option value="">请选择具体条款</option>
            <option v-for="c in clauses" :key="c.code" :value="c.code">{{ c.code }} · {{ c.title }}</option>
          </select>
          <button v-if="issueValues['违章条款']" class="link clause-preview" type="button" @click="openClause(issueValues['违章条款'])">
            预览条款全文
          </button>
        </label>
        <label class="form-row">
          <span>整改要求<i>*</i></span>
          <textarea v-model="issueValues['整改要求']" rows="2" placeholder="写清整改动作与验收口径"></textarea>
        </label>
        <label class="form-row">
          <span>整改期限<i>*</i></span>
          <input v-model="issueValues['整改期限']" type="date" :min="todayStr" />
        </label>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="issuing = false">取消</button>
          <button class="btn primary" type="submit">下达整改</button>
        </footer>
      </form>
    </div>

    <!-- 确认闭合 -->
    <div v-if="closing" class="modal-mask" @click.self="closing = false">
      <form class="modal" @submit.prevent="submitClose">
        <h3>确认闭合 · {{ closingEntry?.['监察编号'] }}</h3>
        <label class="form-row">
          <span>整改责任人<i>*</i></span>
          <input v-model="closeValues['整改人']" placeholder="谁完成的整改" />
        </label>
        <label class="form-row">
          <span>闭合备注</span>
          <textarea v-model="closeValues['note']" rows="2" placeholder="复查情况（可选）"></textarea>
        </label>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closing = false">取消</button>
          <button class="btn primary" type="submit">确认闭合（闭合后锁定）</button>
        </footer>
      </form>
    </div>

    <!-- 条款全文 -->
    <div v-if="activeClause" class="modal-mask" @click.self="activeClause = null">
      <div class="modal">
        <h3>{{ activeClause.title }}</h3>
        <p class="clause-code">条款编号：{{ activeClause.code }} · {{ activeClause.category }}</p>
        <p class="clause-content">{{ activeClause.content }}</p>
        <footer class="modal-foot">
          <button class="btn primary" type="button" @click="activeClause = null">知道了</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const ENDPOINT = '/api/qualitycheck'
const session = useSessionStore()

type Node = { time: string; action: string; operator: string; note?: string; auto?: boolean }
type Entry = {
  id: number
  status: string
  overdue?: boolean
  timeline?: Node[]
  [key: string]: string | number | boolean | Node[] | null | undefined
}
type Stage = { stage: string; entries: Entry[] }
type Clause = { code: string; title: string; category: string; content: string }

const STAGES = ['待监察', '监察中', '待整改', '已闭合']

const stages = ref<Stage[]>(STAGES.map((stage) => ({ stage, entries: [] })))
const total = ref(0)
const overdueCount = ref(0)
const month = ref(new Date().toISOString().slice(0, 7))
const message = ref('')
const clauses = ref<Clause[]>([])

const todayStr = new Date().toISOString().slice(0, 10)

const stats = computed(() => [
  { label: '监察记录总数', value: total.value, danger: false },
  {
    label: '逾期未整改',
    value: overdueCount.value,
    danger: overdueCount.value > 0,
  },
  { label: '待整改记录', value: stageCount('待整改'), danger: false },
  { label: '已闭合记录', value: stageCount('已闭合'), danger: false },
])

function stageCount(name: string): number {
  return stages.value.find((s) => s.stage === name)?.entries.length ?? 0
}

function stageClass(stage: string): string {
  return { 待监察: 'gray', 监察中: 'blue', 待整改: 'amber', 已闭合: 'green' }[stage] ?? 'gray'
}

function overdueDays(entry: Entry): number {
  const due = String(entry['整改期限'] ?? '').slice(0, 10)
  if (!due) return 0
  const diff = Date.parse(todayStr) - Date.parse(due)
  return Math.max(0, Math.floor(diff / 86_400_000))
}

async function reload() {
  message.value = ''
  const query = new URLSearchParams()
  if (month.value) query.set('month', month.value)
  try {
    const response = await request(`${ENDPOINT}/timeline?${query.toString()}`)
    if (!response.ok) throw new Error('时间轴读取失败')
    const payload = await response.json()
    // 始终保持四阶段竖排，即使某阶段为空
    stages.value = STAGES.map((name) => {
      const found = (payload.stages ?? []).find((s: Stage) => s.stage === name)
      return { stage: name, entries: found?.entries ?? [] }
    })
    total.value = payload.total ?? 0
    overdueCount.value = payload.overdue ?? 0
  } catch (error) {
    message.value = error instanceof Error ? error.message : '时间轴读取失败'
  }
}

async function loadClauses() {
  try {
    const response = await request(`${ENDPOINT}/clauses`)
    if (response.ok) {
      const payload = await response.json()
      clauses.value = payload.items ?? []
    }
  } catch {
    clauses.value = []
  }
}

// ---------- 登记 ----------
const creating = ref(false)
const createForm = [
  { key: '监察编号', label: '监察编号', required: true, placeholder: 'QUAL-0xxx' },
  { key: '监察日期', label: '监察日期', required: true, placeholder: 'YYYY-MM-DD' },
  { key: '监察区域', label: '监察区域', required: true, placeholder: '如 T1 加油区' },
  { key: '监察事项', label: '监察事项', required: true, placeholder: '本次监察的内容' },
]
const createValues = reactive<Record<string, string>>({
  监察编号: '', 监察日期: todayStr, 监察区域: '', 监察事项: '', 违章条款: '',
})

function openCreate() {
  Object.assign(createValues, {
    监察编号: '', 监察日期: todayStr, 监察区域: '', 监察事项: '', 违章条款: '',
  })
  creating.value = true
}

async function submitCreate() {
  message.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createValues, operator: session.operator } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      message.value = payload?.detail?.[0]?.msg || payload.message || '登记失败'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '登记失败'
  }
}

// ---------- 动作 ----------
async function postAction(id: number, values: Record<string, unknown>) {
  const response = await request(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { operator: session.operator, ...values } }),
  })
  return response.json() as Promise<{ ok: boolean; message: string }>
}

async function runAction(action: string, entry: Entry) {
  message.value = ''
  try {
    const payload = await postAction(entry.id, { action })
    if (!payload.ok) {
      message.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '操作失败'
  }
}

// ---------- 下达整改 ----------
const issuing = ref(false)
const issuingEntry = ref<Entry | null>(null)
const issueValues = reactive<Record<string, string>>({
  发现违章: '', 违章条款: '', 整改要求: '', 整改期限: '',
})

function openIssue(entry: Entry) {
  issuingEntry.value = entry
  Object.assign(issueValues, {
    发现违章: String(entry['发现违章'] ?? ''),
    违章条款: String(entry['违章条款'] ?? ''),
    整改要求: String(entry['整改要求'] ?? ''),
    整改期限: '',
  })
  issuing.value = true
}

async function submitIssue() {
  if (!issuingEntry.value) return
  message.value = ''
  try {
    const payload = await postAction(issuingEntry.value.id, { action: '下达整改', ...issueValues })
    if (!payload.ok) {
      message.value = payload.message
      return
    }
    issuing.value = false
    await reload()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '下达整改失败'
  }
}

// ---------- 确认闭合 ----------
const closing = ref(false)
const closingEntry = ref<Entry | null>(null)
const closeValues = reactive<Record<string, string>>({ 整改人: '', note: '' })

function openClose(entry: Entry) {
  closingEntry.value = entry
  closeValues.整改人 = session.operator
  closeValues.note = ''
  closing.value = true
}

async function submitClose() {
  if (!closingEntry.value) return
  message.value = ''
  try {
    const payload = await postAction(closingEntry.value.id, { action: '确认闭合', ...closeValues })
    if (!payload.ok) {
      message.value = payload.message
      return
    }
    closing.value = false
    await reload()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '闭合失败'
  }
}

// ---------- 条款 ----------
const activeClause = ref<Clause | null>(null)

async function openClause(code: string) {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/clauses/${encodeURIComponent(code)}`)
    if (!response.ok) throw new Error('条款读取失败')
    activeClause.value = await response.json()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '条款读取失败'
  }
}

// ---------- 导出：当月清单，逾期数与页面同口径 ----------
function exportRows() {
  const target = month.value || todayStr.slice(0, 7)
  window.open(`${ENDPOINT}/export?month=${encodeURIComponent(target)}`, '_blank')
}

onMounted(() => {
  void loadClauses()
  void reload()
})
</script>
