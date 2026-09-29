<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常；监察整改逾期会直接回写到下面的待办里。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <section v-if="todos.length" class="todo-panel">
      <h3 class="todo-title">待办预警</h3>
      <RouterLink
        v-for="todo in todos"
        :key="todo.label"
        :to="todo.link"
        class="todo-item"
        :class="{ 'todo-danger': todo.tone === 'danger' }"
      >
        <span>{{ todo.label }}</span>
        <strong>{{ todo.value }}</strong>
      </RouterLink>
    </section>

    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th><th>逾期</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
          <td>
            <span v-if="row.overdue" class="overdue-cell">{{ row.overdue }}</span>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Todo = { label: string; value: number; tone: string; link: string }
type Overview = {
  cards: { label: string; value: number }[]
  todos?: Todo[]
  modules: { name: string; created: number; pending: number; abnormal: number; overdue?: number }[]
}

const cards = ref<Overview['cards']>([])
const todos = ref<Todo[]>([])
const moduleRows = ref<Overview['modules']>([])

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    todos.value = payload.todos ?? []
    moduleRows.value = payload.modules
  } catch {
    cards.value = [{ label: '业务模块', value: 0 }, { label: '今日新增', value: 0 }]
    moduleRows.value = []
  }
})
</script>

<style scoped>
.todo-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.todo-title { margin: 0 0 8px; font-size: 14px; }
.todo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  text-decoration: none;
  color: inherit;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 6px;
  font-size: 13px;
}
.todo-item:last-child { margin-bottom: 0; }
.todo-danger { border-color: #f0a5a0; background: #fff5f4; }
.todo-danger strong { color: #b42318; font-size: 18px; }
.overdue-cell {
  color: #b42318;
  background: #fdecea;
  border-radius: 10px;
  padding: 1px 9px;
  font-weight: 600;
}
</style>
