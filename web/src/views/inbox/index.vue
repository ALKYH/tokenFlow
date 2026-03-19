<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchMarketplaceInbox } from '@/service/api';
import { getLocale } from '@/locales';
import MessageCard from './MessageCard.vue';

const tabs = ['All', 'marketplace', 'routing', 'workspace'];
const activeTab = ref('All');
const query = ref('');
const page = ref(1);
const pageSize = ref(10);
const msgs = ref<any[]>([]);
const selectedIds = ref(new Set<string>());
const isZh = computed(() => getLocale() === 'zh-CN');

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  return msgs.value.filter(
    item =>
      (activeTab.value === 'All' || item.category === activeTab.value) &&
      (!q || `${item.title} ${item.body}`.toLowerCase().includes(q))
  );
});

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const paged = computed(() => {
  page.value = Math.min(page.value, pageCount.value);
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
});

function toggleSelect(id: string) {
  if (selectedIds.value.has(id)) selectedIds.value.delete(id);
  else selectedIds.value.add(id);
}

function markRead() {
  msgs.value = msgs.value.map(item => (selectedIds.value.has(String(item.id)) ? { ...item, is_read: true } : item));
  selectedIds.value.clear();
}

function removeSelected() {
  msgs.value = msgs.value.filter(item => !selectedIds.value.has(String(item.id)));
  selectedIds.value.clear();
}

function openMessage(message: any) {
  window.$dialog?.info({
    title: message.title,
    content: message.body,
    positiveText: 'Close'
  });
}

onMounted(async () => {
  try {
    msgs.value = await fetchMarketplaceInbox();
  } catch {
    msgs.value = [];
  }
});
</script>

<template>
  <div class="inbox-page">
    <div class="hero-card">
      <div>
        <div class="hero-kicker">Inbox</div>
        <div class="hero-title">{{ isZh ? '最新消息' : 'Latest Messages' }}</div>
        <div class="hero-desc">{{ isZh ? '集中查看市场、路由和工作区更新。' : 'Review market, routing and workspace updates, then triage them in one place.' }}</div>
      </div>
      <NTag type="info" round>{{ msgs.length }} {{ isZh ? '条消息' : 'messages' }}</NTag>
    </div>

    <div class="header-row">
      <n-input v-model:value="query" size="medium" :placeholder="isZh ? '搜索消息' : 'Search messages'" clearable style="flex:1">
        <template #suffix>
          <n-select v-model:value="activeTab" :options="tabs.map(t => ({ label: t, value: t }))" size="small" style="width:140px" />
        </template>
      </n-input>
      <div class="toolbar-actions">
        <n-button size="small" @click="markRead">{{ isZh ? '标记已读' : 'Mark Read' }}</n-button>
        <n-button size="small" tertiary @click="removeSelected">{{ isZh ? '删除' : 'Delete' }}</n-button>
      </div>
    </div>

    <div class="list-area">
      <div v-if="filtered.length === 0" class="empty">{{ isZh ? '暂无消息' : 'No messages' }}</div>
      <div v-else>
        <MessageCard
          v-for="m in paged"
          :key="m.id"
          :message="{
            ...m,
            id: String(m.id),
            subject: m.title,
            snippet: m.body,
            fileType: m.channel,
            module: m.category,
            date: new Date(m.created_at || Date.now()).getTime()
          }"
          :selected="selectedIds.has(String(m.id))"
          @toggle="toggleSelect"
          @open="openMessage"
        />
      </div>
    </div>

    <div class="pager-row">
      <div class="summary">{{ isZh ? '已选' : 'Selected' }} {{ selectedIds.size }}</div>
      <n-pagination :page="page" :page-count="pageCount" @update:page="p => page = p" />
    </div>
  </div>
</template>

<style scoped>
.inbox-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.hero-kicker,
.hero-desc,
.summary {
  color: #64748b;
  font-size: 12px;
}

.hero-title {
  margin: 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.header-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.toolbar-actions {
  margin-left: 12px;
  display: flex;
  gap: 8px;
}

.list-area {
  background: var(--n-card-color, #fff);
  border-radius: 16px;
  padding: 8px;
  max-height: 60vh;
  overflow: auto;
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.empty {
  padding: 40px;
  text-align: center;
  color: var(--n-text-3);
}

.pager-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

@media (prefers-color-scheme: dark) {
  .hero-card,
  .list-area {
    background: rgba(15, 23, 42, 0.82);
    border-color: rgba(71, 85, 105, 0.3);
  }

  .hero-title {
    color: #e2e8f0;
  }

  .hero-kicker,
  .hero-desc,
  .summary {
    color: #94a3b8;
  }
}
</style>
