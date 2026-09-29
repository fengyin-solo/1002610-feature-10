<template>
  <section class="page" data-module="qualitycheck">
    <header class="page-head">
      <div>
        <h2>质量监察管理</h2>
        <p class="page-desc">监察记录按待监察、监察中、待整改、已闭合四个阶段摊到时间轴上；逾期记录标红并自动退回待整改，谁在什么时间改的都写在节点上。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记监察记录</button>
        <button class="btn" type="button" @click="openClauses('')">违章条款库</button>
        <button class="btn" type="button" @click="exportRows">导出当月监察清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card" :class="{ 'stat-danger': item.danger }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'text-danger': item.danger }">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>监察月份</span>
        <input v-model="month" type="month" />
      </label>
      <label class="filter-item keyword">
        <span>监察编号 / 区域</span>
        <input v-model="keyword" placeholder="按监察编号或区域检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="timeline">
      <article
        v-for="stage in stages"
        :key="stage.status"
        class="timeline-stage"
        :class="{ 'stage-danger': stage.overdue > 0 }"
      >
        <header class="stage-head">
          <span class="stage-name">{{ stage.status }}</span>
          <span class="stage-count">{{ stage.count }} 条</span>
          <span v-if="stage.overdue" class="stage-overdue">逾期 {{ stage.overdue }}</span>
        </header>

        <div class="stage-body">
          <div class="stage-line" />
          <div v-if="!stage.entries.length" class="stage-empty">该阶段暂无记录</div>

          <div
            v-for="entry in stage.entries"
            :key="entry.id"
            class="record-card"
            :class="{ overdue: entry.overdue, closed: entry.status === '已闭合' }"
          >
            <div class="record-head">
              <span class="record-code">{{ entry['监察编号'] }}</span>
              <span v-if="entry.overdue" class="tag tag-danger">逾期 {{ entry['逾期天数'] }} 天</span>
              <span v-if="entry.status === '已闭合'" class="tag tag-closed">已锁定</span>
            </div>
            <p class="record-line"><b>区域</b>{{ entry['监察区域'] }}</p>
            <p class="record-line"><b>事项</b>{{ entry['监察事项'] }}</p>
            <p v-if="entry['发现违章']" class="record-line">
              <b>违章</b>{{ entry['发现违章'] }}
              <button class="link clause-link" type="button" @click="openClauses(String(entry['违章条款'] ?? ''))">
                {{ entry['违章条款'] }}<template v-if="entry['条款名称']"> · {{ entry['条款名称'] }}</template>
              </button>
            </p>
            <p class="record-line"><b>期限</b>
              <span :class="{ 'text-danger': entry.overdue }">{{ entry['整改期限'] || '—' }}</span>
            </p>
            <footer class="record-foot">
              <span>{{ entry['监察日期'] }}</span>
              <span class="record-links">
                <button class="link" type="button" @click="openDetail(entry)">时间轴</button>
                <button
                  v-for="action in contextActions(entry)"
                  :key="action"
                  class="link"
                  type="button"
                  @click="openAction(action, entry)"
                >{{ action }}</button>
                <button
                  v-if="entry.status !== '已闭合'"
                  class="link"
                  type="button"
                  @click="openEdit(entry)"
                >编辑</button>
              </span>
            </footer>
          </div>
        </div>
      </article>
    </div>

    <footer class="page-foot">
      <span>{{ month }} 共 {{ total }} 条监察记录，逾期 <b :class="{ 'text-danger': overdueCount > 0 }">{{ overdueCount }}</b> 条</span>
      <span v-if="reconcileText" class="reconcile-text">{{ reconcileText }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记 / 编辑 -->
    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3>{{ formMode === 'create' ? '登记监察记录' : '编辑监察记录' }}</h3>
        <p v-if="editingClosed" class="error-text">该记录已闭合，不再接受任何修改。</p>
        <div class="form-grid">
          <label v-for="field in formFields" :key="field.key" class="form-item" :class="{ wide: field.wide }">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <textarea
              v-if="field.textarea"
              v-model="formValues[field.key]"
              rows="2"
              :disabled="editingClosed"
            />
            <input
              v-else
              v-model="formValues[field.key]"
              :type="field.type || 'text'"
              :disabled="editingClosed"
              :placeholder="field.placeholder || ''"
            />
          </label>
          <label class="form-item">
            <span>违章条款（发现违章时必选）</span>
            <select v-model="formValues['违章条款']" :disabled="editingClosed">
              <option value="">无违章 / 待关联</option>
              <option v-for="clause in clauses" :key="clause.code" :value="clause.code">
                {{ clause.code }} · {{ clause.name }}
              </option>
            </select>
          </label>
        </div>
        <p v-if="formValues['发现违章'] && !formValues['违章条款']" class="error-text form-hint">
          已填写发现违章，必须点选一条具体条款才能保存。
        </p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="button" :disabled="editingClosed" @click="submitForm">
            {{ formMode === 'create' ? '登记' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 动作弹窗 -->
    <div v-if="actionVisible" class="modal-mask" @click.self="closeAction">
      <div class="modal">
        <h3>{{ actionMode }} · {{ actionEntry?.['监察编号'] }}</h3>
        <div v-if="actionMode === '下达整改'" class="form-grid">
          <label class="form-item wide">
            <span>整改要求<em>*</em></span>
            <textarea v-model="actionValues['整改要求']" rows="2" />
          </label>
          <label class="form-item">
            <span>整改期限<em>*</em></span>
            <input v-model="actionValues['整改期限']" type="date" />
          </label>
        </div>
        <div v-else-if="actionMode === '提交整改'" class="form-grid">
          <label class="form-item">
            <span>整改人</span>
            <input v-model="actionValues['整改人']" :placeholder="session.operator" />
          </label>
          <label class="form-item wide">
            <span>整改情况<em>*</em></span>
            <textarea v-model="actionValues['整改情况']" rows="3" />
          </label>
        </div>
        <p v-else class="modal-tip">
          {{ actionMode === '开展监察' ? '确认监察人员已到岗，记录进入监察中。' : '闭合后记录将被锁定，不再接受任何修改。' }}
        </p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeAction">取消</button>
          <button class="btn primary" type="button" @click="submitAction">确认{{ actionMode }}</button>
        </div>
      </div>
    </div>

    <!-- 详情 / 时间轴 -->
    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-wide">
        <h3>{{ detailEntry?.['监察编号'] }} · 时间轴</h3>
        <div v-if="detailEntry" class="detail-grid">
          <p><b>监察区域</b>{{ detailEntry['监察区域'] }}</p>
          <p><b>监察日期</b>{{ detailEntry['监察日期'] }}</p>
          <p><b>当前状态</b>{{ detailEntry['status'] }}</p>
          <p><b>整改期限</b>
            <span :class="{ 'text-danger': detailEntry.overdue }">{{ detailEntry['整改期限'] || '—' }}</span>
          </p>
          <p class="detail-wide"><b>监察事项</b>{{ detailEntry['监察事项'] }}</p>
          <p v-if="detailEntry['发现违章']" class="detail-wide">
            <b>发现违章</b>{{ detailEntry['发现违章'] }}
            <button class="link" type="button" @click="openClauses(String(detailEntry['违章条款'] ?? ''))">
              {{ detailEntry['违章条款'] }} · {{ detailEntry['条款名称'] }}
            </button>
          </p>
          <p v-if="detailEntry['整改要求']" class="detail-wide"><b>整改要求</b>{{ detailEntry['整改要求'] }}</p>
          <p v-if="detailEntry['整改情况']" class="detail-wide"><b>整改情况</b>{{ detailEntry['整改情况'] }}（{{ detailEntry['整改人'] || '—' }}）</p>
        </div>
        <ol class="node-list">
          <li
            v-for="(node, index) in detailEntry?.timeline ?? []"
            :key="index"
            class="node-item"
            :class="{ 'node-danger': node.action === '逾期自动退回' }"
          >
            <span class="node-dot" />
            <div>
              <p class="node-title">
                {{ node.action }}
                <em v-if="node.action === '逾期自动退回'" class="text-danger">系统自动退回待整改</em>
              </p>
              <p class="node-meta">{{ node.actor }} · {{ node.time }}</p>
              <p v-if="node.note" class="node-note">{{ node.note }}</p>
            </div>
          </li>
        </ol>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <!-- 条款库 -->
    <div v-if="clauseVisible" class="modal-mask" @click.self="closeClauses">
      <div class="modal modal-wide">
        <h3>违章条款库</h3>
        <p class="modal-tip">监察记录里的违章内容必须点到以下某一条具体条款。</p>
        <table class="data-table clause-table">
          <thead>
            <tr><th>条款编号</th><th>条款名称</th><th>制度依据</th><th>违章描述</th><th>整改指引</th></tr>
          </thead>
          <tbody>
            <tr v-for="clause in clauses" :key="clause.code" :class="{ 'clause-active': clause.code === activeClauseCode }">
              <td>{{ clause.code }}</td>
              <td>{{ clause.name }}</td>
              <td>{{ clause.basis }}</td>
              <td>{{ clause.description }}</td>
              <td>{{ clause.guide }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeClauses">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const ENDPOINT = '/api/qualitycheck'
const session = useSessionStore()

type TimelineNode = { action: string; actor: string; time: string; note: string }
type RecordEntry = Record<string, string | number | boolean | TimelineNode[] | null> & {
  id: number
  status: string
  overdue: boolean
  timeline: TimelineNode[]
}
type Stage = { status: string; count: number; overdue: number; entries: RecordEntry[] }
type Clause = { code: string; name: string; basis: string; description: string; guide: string }

const stages = ref<Stage[]>([])
const total = ref(0)
const overdueCount = ref(0)
const month = ref(new Date().toISOString().slice(0, 7))
const keyword = ref('')
const errorMessage = ref('')
const reconcileText = ref('')
const clauses = ref<Clause[]>([])

const statCards = computed(() => [
  { label: '待监察', value: stages.value.find(s => s.status === '待监察')?.count ?? 0, danger: false },
  { label: '监察中', value: stages.value.find(s => s.status === '监察中')?.count ?? 0, danger: false },
  { label: '待整改', value: stages.value.find(s => s.status === '待整改')?.count ?? 0, danger: false },
  { label: '已闭合', value: stages.value.find(s => s.status === '已闭合')?.count ?? 0, danger: false },
  { label: '本月逾期', value: overdueCount.value, danger: overdueCount.value > 0 },
])

const formFields = [
  { key: '监察日期', label: '监察日期', required: true, type: 'date' },
  { key: '监察区域', label: '监察区域', required: true, placeholder: '如：203 号机位' },
  { key: '监察事项', label: '监察事项', required: true, wide: true },
  { key: '发现违章', label: '发现违章', wide: true, textarea: true, placeholder: '没有违章可留空' },
  { key: '整改要求', label: '整改要求', wide: true, textarea: true, placeholder: '可在下达整改时再填写' },
  { key: '整改期限', label: '整改期限', type: 'date' },
]

// --------------------------------------------------------------- 时间轴数据

async function reload() {
  errorMessage.value = ''
  reconcileText.value = ''
  const query = new URLSearchParams({ month: month.value })
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  try {
    const response = await request(`${ENDPOINT}/timeline?${query.toString()}`)
    if (!response.ok) throw new Error('时间轴数据读取失败')
    const payload = await response.json()
    stages.value = payload.stages ?? []
    total.value = payload.total ?? 0
    overdueCount.value = payload.overdueCount ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质量监察时间轴读取失败'
  }
}

function resetFilters() {
  month.value = new Date().toISOString().slice(0, 7)
  keyword.value = ''
  void reload()
}

// --------------------------------------------------------------- 记录操作

function contextActions(entry: RecordEntry): string[] {
  switch (entry.status) {
    case '待监察':
      return ['开展监察']
    case '监察中':
      return ['下达整改']
    case '待整改':
      return ['提交整改', '确认闭合']
    default:
      return []
  }
}

// 登记 / 编辑
const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const editingClosed = ref(false)
const formValues = ref<Record<string, string>>({})

function emptyForm(): Record<string, string> {
  return {
    监察日期: month.value ? `${month.value}-01` : '',
    监察区域: '',
    监察事项: '',
    发现违章: '',
    违章条款: '',
    整改要求: '',
    整改期限: '',
  }
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  editingClosed.value = false
  formValues.value = emptyForm()
  formVisible.value = true
}

function openEdit(entry: RecordEntry) {
  if (entry.status === '已闭合') {
    errorMessage.value = '该记录已闭合，不再接受任何修改'
    return
  }
  formMode.value = 'edit'
  editingId.value = entry.id
  editingClosed.value = false
  formValues.value = {
    监察日期: String(entry['监察日期'] ?? ''),
    监察区域: String(entry['监察区域'] ?? ''),
    监察事项: String(entry['监察事项'] ?? ''),
    发现违章: String(entry['发现违章'] ?? ''),
    违章条款: String(entry['违章条款'] ?? ''),
    整改要求: String(entry['整改要求'] ?? ''),
    整改期限: String(entry['整改期限'] ?? ''),
  }
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  errorMessage.value = ''
  const url = formMode.value === 'create'
    ? ENDPOINT
    : `${ENDPOINT}/${editingId.value}`
  const method = formMode.value === 'create' ? 'POST' : 'PATCH'
  try {
    const response = await request(url, {
      method,
      body: JSON.stringify({ values: { ...formValues.value, operator: session.operator } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '保存失败')
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '监察记录保存失败'
  }
}

// 动作弹窗
const actionVisible = ref(false)
const actionMode = ref('')
const actionEntry = ref<RecordEntry | null>(null)
const actionValues = ref<Record<string, string>>({})

function openAction(action: string, entry: RecordEntry) {
  if (entry.status === '已闭合') {
    errorMessage.value = '该记录已闭合，不再接受任何修改'
    return
  }
  actionMode.value = action
  actionEntry.value = entry
  actionValues.value = {
    整改要求: String(entry['整改要求'] ?? ''),
    整改期限: String(entry['整改期限'] ?? ''),
    整改人: String(entry['整改人'] ?? ''),
    整改情况: String(entry['整改情况'] ?? ''),
  }
  actionVisible.value = true
}

function closeAction() {
  actionVisible.value = false
  actionEntry.value = null
}

async function submitAction() {
  errorMessage.value = ''
  if (!actionEntry.value) return
  try {
    const response = await request(`${ENDPOINT}/${actionEntry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action: actionMode.value, ...actionValues.value, operator: session.operator },
      }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '操作未生效')
    }
    actionVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质量监察操作失败'
  }
}

// 详情 / 时间轴
const detailVisible = ref(false)
const detailEntry = ref<RecordEntry | null>(null)

async function openDetail(entry: RecordEntry) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entry.id}`)
    if (!response.ok) throw new Error('监察记录明细读取失败')
    detailEntry.value = await response.json()
    detailVisible.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '监察记录明细读取失败'
  }
}

function closeDetail() {
  detailVisible.value = false
}

// 条款库
const clauseVisible = ref(false)
const activeClauseCode = ref('')

async function loadClauses(activeCode = '') {
  if (!clauses.value.length) {
    try {
      const response = await request(`${ENDPOINT}/clauses`)
      if (response.ok) {
        const payload = await response.json()
        clauses.value = payload.items ?? []
      }
    } catch {
      // 条款读不出来时保留为空列表，表单仍可录入其它字段
    }
  }
  activeClauseCode.value = activeCode
  clauseVisible.value = true
}

function openClauses(code?: string) {
  void loadClauses(typeof code === 'string' ? code : '')
}

function closeClauses() {
  clauseVisible.value = false
}

// 导出：下载当月清单，并拿响应头里的统计数和页面做对账
async function exportRows() {
  errorMessage.value = ''
  reconcileText.value = ''
  try {
    const response = await request(`${ENDPOINT}/export?month=${encodeURIComponent(month.value)}`)
    if (!response.ok) throw new Error('当月监察清单导出失败')
    const exportedTotal = Number(response.headers.get('X-Export-Total') ?? '0')
    const exportedOverdue = Number(response.headers.get('X-Export-Overdue') ?? '0')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `质量监察清单-${month.value}.csv`
    link.click()
    URL.revokeObjectURL(url)
    if (exportedOverdue === overdueCount.value && exportedTotal === total.value) {
      reconcileText.value = `导出对账一致：清单共 ${exportedTotal} 条，逾期 ${exportedOverdue} 条`
    } else {
      reconcileText.value = `导出对账异常：页面 ${total.value}/${overdueCount.value}，清单 ${exportedTotal}/${exportedOverdue}`
      errorMessage.value = '导出清单上的逾期数与页面不一致，请刷新后重试'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '当月监察清单导出失败'
  }
}

onMounted(() => {
  void loadClauses()
  clauseVisible.value = false
  void reload()
})
</script>

<style scoped>
.text-danger { color: #b42318; }
.stat-danger { border-color: #f0a5a0; background: #fff5f4; }

.timeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}
.timeline-stage {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  min-height: 320px;
}
.timeline-stage.stage-danger { border-color: #f0a5a0; }
.stage-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: #fff;
  border-radius: 8px 8px 0 0;
}
.stage-name { font-weight: 600; }
.stage-count { color: var(--muted); font-size: 12px; }
.stage-overdue {
  margin-left: auto;
  font-size: 12px;
  color: #b42318;
  background: #fdecea;
  border-radius: 10px;
  padding: 1px 8px;
}
.stage-body { position: relative; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.stage-line {
  position: absolute;
  left: 19px;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: #e2e8f0;
}
.stage-empty { position: relative; color: var(--muted); font-size: 12px; padding: 8px 4px 8px 18px; }

.record-card {
  position: relative;
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
}
.record-card.overdue { border-color: #f0a5a0; border-left-color: #d92d20; background: #fff7f6; }
.record-card.closed { border-left-color: #94a3b8; background: #f8fafc; }
.record-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.record-code { font-weight: 600; font-size: 13px; }
.tag { font-size: 11px; border-radius: 10px; padding: 1px 7px; }
.tag-danger { color: #b42318; background: #fdecea; }
.tag-closed { color: #475569; background: #e2e8f0; }
.record-line { margin: 2px 0; font-size: 12px; line-height: 1.5; }
.record-line b { display: inline-block; color: var(--muted); width: 40px; font-style: normal; }
.clause-link { font-size: 12px; margin-left: 4px; }
.record-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  color: var(--muted);
  font-size: 11px;
}
.record-links { display: flex; gap: 8px; flex-wrap: wrap; }

.filter-item.keyword { flex: 1; min-width: 200px; }
.reconcile-text { color: #067647; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: 86vh;
  overflow-y: auto;
  padding: 18px 20px;
}
.modal-wide { width: 880px; }
.modal h3 { margin: 0 0 12px; font-size: 16px; }
.modal-tip { color: var(--muted); font-size: 13px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.form-item.wide { grid-column: 1 / -1; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item em { color: #b42318; font-style: normal; margin-left: 2px; }
.form-item input,
.form-item textarea,
.form-item select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
  font-size: 13px;
}
.form-hint { margin: 8px 0 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 16px;
  font-size: 13px;
  margin-bottom: 12px;
}
.detail-grid p { margin: 3px 0; }
.detail-grid .detail-wide { grid-column: 1 / -1; }
.detail-grid b { color: var(--muted); font-weight: normal; margin-right: 8px; }

.node-list { list-style: none; margin: 0; padding: 4px 0 0; }
.node-item { position: relative; padding: 0 0 14px 22px; }
.node-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 14px;
  bottom: -2px;
  width: 2px;
  background: #e2e8f0;
}
.node-item:last-child::before { display: none; }
.node-dot {
  position: absolute;
  left: 0;
  top: 4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--brand);
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px var(--brand);
}
.node-item.node-danger .node-dot { background: #d92d20; box-shadow: 0 0 0 1px #d92d20; }
.node-title { margin: 0; font-size: 13px; font-weight: 600; }
.node-title em { font-style: normal; font-size: 12px; margin-left: 8px; }
.node-meta { margin: 2px 0; font-size: 12px; color: var(--muted); }
.node-note { margin: 2px 0 0; font-size: 12px; }

.clause-table { margin-top: 8px; }
.clause-table td { vertical-align: top; }
.clause-active { background: #eff6ff; }
</style>
