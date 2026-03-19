<script setup lang="ts">
const props = defineProps<{ item: any; installed?: boolean }>();
const emit = defineEmits<{
  (e: 'open', payload: any): void
  (e: 'install', payload: any): void
}>();
</script>

<template>
  <div class="market-card">
    <div class="icon-wrap" @click="emit('open', item)">
      <img v-if="item.icon" :src="item.icon" alt="icon" />
      <div v-else class="icon-fallback">{{ item.name?.[0] || '?' }}</div>
    </div>

    <div class="content" @click="emit('open', item)">
      <div class="title-row">
        <div class="title">{{ item.name }}</div>
        <NTag round size="small" :type="installed ? 'success' : 'info'">{{ installed ? '已导入' : item.category }}</NTag>
      </div>
      <div class="meta">作者：<span class="author">{{ item.author_name || item.author || 'Unknown' }}</span></div>
      <div class="desc">{{ item.summary || item.description }}</div>
      <div class="tag-row">
        <NTag v-for="tag in (item.tags || []).slice(0, 3)" :key="tag" size="small" round>{{ tag }}</NTag>
      </div>
      <div class="stats">
        <span>{{ item.installs || 0 }} installs</span>
        <span>{{ item.downloads || 0 }} downloads</span>
      </div>
    </div>

    <div class="actions">
      <NButton size="small" type="primary" :disabled="installed" @click="emit('install', item)">
        {{ installed ? '已导入库' : '导入模块库' }}
      </NButton>
    </div>
  </div>
</template>

<style scoped>
.market-card {
  display: grid;
  grid-template-columns: 60px 1fr auto;
  gap: 14px;
  align-items: start;
  padding: 14px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  box-shadow: 0 6px 14px rgba(13, 38, 59, 0.04);
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}

.market-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 30px rgba(13, 38, 59, 0.08);
  border-color: rgba(59, 130, 246, 0.22);
}

.icon-wrap {
  width: 60px;
  height: 60px;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f5f7fa, #eef3ff);
  cursor: pointer;
}

.icon-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.icon-fallback {
  font-weight: 700;
  color: var(--n-text-1, #111);
  font-size: 22px;
}

.content {
  min-width: 0;
  cursor: pointer;
}

.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.title {
  font-weight: 700;
  color: var(--n-text-1, #111);
}

.meta,
.stats {
  font-size: 12px;
  color: var(--n-text-3, #666);
  margin-top: 6px;
}

.author {
  color: var(--n-text-2, #2a7ae2);
}

.desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--n-text-2, #444);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.6;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.stats {
  display: flex;
  gap: 12px;
}

.actions {
  display: flex;
  align-items: center;
}

@media (prefers-color-scheme: dark) {
  .market-card {
    background: rgba(15, 23, 42, 0.78);
    border-color: rgba(71, 85, 105, 0.32);
  }

  .icon-wrap {
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.92), rgba(30, 64, 175, 0.26));
  }
}
</style>
