<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  fetchMarketplacePlugins,
  getStoredAccessToken,
  importPluginToWorkspaceLibrary,
  installMarketplacePlugin,
  loadInstalledMarketLibrary,
  loadWorkspaceSnapshots
} from '@/service/api';
import { getLocale } from '@/locales';
import ResultCard from './ResultCard.vue';

const tabs = [
  { label: 'All', value: 'all' },
  { label: 'Knowledge', value: 'knowledge' },
  { label: 'Tools', value: 'tools' },
  { label: 'Routing', value: 'routing' },
  { label: 'My Library', value: 'library' }
];

const activeTab = ref('all');
const query = ref('');
const sortBy = ref('popular');
const page = ref(1);
const pageSize = ref(6);
const loading = ref(false);
const marketItems = ref<any[]>([]);
const localModules = ref<any[]>([]);
const installedSlugs = ref<string[]>([]);
const isZh = computed(() => getLocale() === 'zh-CN');

const sortOptions = [
  { label: 'Popular', value: 'popular' },
  { label: 'Newest', value: 'newest' },
  { label: 'Name', value: 'name' }
];

async function loadMarketplace() {
  loading.value = true;
  try {
    marketItems.value = await fetchMarketplacePlugins({ q: query.value, category: activeTab.value === 'library' ? undefined : activeTab.value });
  } catch {
    marketItems.value = [];
  } finally {
    loading.value = false;
  }
}

function loadLocalLibrary() {
  installedSlugs.value = loadInstalledMarketLibrary().map((item: any) => item.slug);
  localModules.value = loadWorkspaceSnapshots();
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  const base =
    activeTab.value === 'library'
      ? localModules.value.map((item: any) => ({
          id: item.id,
          name: item.name,
          summary: item.description,
          category: 'library',
          author_name: 'Me',
          installs: item.stats?.nodes || 0,
          downloads: item.stats?.edges || 0,
          slug: item.id,
          tags: ['workspace']
        }))
      : marketItems.value.filter(item => activeTab.value === 'all' || item.category === activeTab.value);

  const byQuery = q ? base.filter(item => JSON.stringify(item).toLowerCase().includes(q)) : base.slice();
  if (sortBy.value === 'name') return byQuery.sort((a, b) => String(a.name).localeCompare(String(b.name)));
  if (sortBy.value === 'newest') return byQuery.sort((a, b) => String(b.updated_at || b.updatedAt || '').localeCompare(String(a.updated_at || a.updatedAt || '')));
  return byQuery.sort((a, b) => (b.installs || 0) - (a.installs || 0));
});

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const pagedResults = computed(() => {
  page.value = Math.min(page.value, pageCount.value);
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
});

async function handleInstall(item: any) {
  try {
    if (item.id && activeTab.value !== 'library') {
      const token = getStoredAccessToken();
      const result = await installMarketplacePlugin(item.id, token || undefined);
      importPluginToWorkspaceLibrary(result.plugin);
    } else {
      importPluginToWorkspaceLibrary(item);
    }
    window.$message?.success(isZh.value ? '已导入到个人模块库' : 'Imported into your module library');
    loadLocalLibrary();
  } catch {
    if (item?.workspace_snapshot || item?.graph) {
      importPluginToWorkspaceLibrary(item);
      loadLocalLibrary();
      window.$message?.warning(isZh.value ? '后端不可用，已切换为本地导入' : 'Backend unavailable, imported locally instead');
    } else {
      window.$message?.error(isZh.value ? '导入失败' : 'Import failed');
    }
  }
}

function openItem(item: any) {
  window.$dialog?.info({
    title: item.name,
    content: item.summary || item.description || 'No description',
    positiveText: 'Close'
  });
}

onMounted(() => {
  loadMarketplace();
  loadLocalLibrary();
});
</script>

<template>
  <div class="marketplace-view">
    <div class="hero-card">
      <div>
        <div class="hero-kicker">Community Market</div>
        <div class="hero-title">{{ isZh ? '模块与插件市场' : 'Modules And Plugins' }}</div>
        <div class="hero-desc">{{ isZh ? '浏览官方与社区模块，并将它们导入到你自己的本地模块库。' : 'Browse official and community packages, then import them into your own local module library.' }}</div>
      </div>
      <div class="hero-stats">
        <NTag type="info" round>Market {{ marketItems.length }}</NTag>
        <NTag type="success" round>Library {{ localModules.length }}</NTag>
      </div>
    </div>

    <div class="toolbar">
      <n-input v-model:value="query" size="medium" :placeholder="isZh ? '搜索模块、插件或工作流' : 'Search packages, modules or workflows'" clearable @update:value="loadMarketplace">
        <template #suffix>
          <n-select v-model:value="sortBy" :options="sortOptions" size="small" style="width:130px;" />
        </template>
      </n-input>
    </div>

    <n-tabs v-model:value="activeTab" animated @update:value="loadMarketplace">
      <n-tab-pane v-for="tab in tabs" :key="tab.value" :name="tab.value" :tab="tab.label">
        <div class="tab-body">
          <NSpin :show="loading">
            <div class="result-grid">
              <ResultCard
                v-for="it in pagedResults"
                :key="it.slug || it.id"
                :item="it"
                :installed="installedSlugs.includes(it.slug)"
                @open="openItem"
                @install="handleInstall"
              />
            </div>
          </NSpin>

          <div class="pager-row">
            <div class="count">{{ isZh ? '共' : 'Total' }} {{ filtered.length }}</div>
            <n-pagination :page="page" :page-count="pageCount" @update:page="p => page = p" />
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.marketplace-view {
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
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.9));
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.hero-kicker,
.hero-desc,
.count {
  color: #64748b;
  font-size: 12px;
}

.hero-title {
  margin: 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.tab-body {
  padding-top: 12px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}

.pager-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

@media (prefers-color-scheme: dark) {
  .hero-card {
    background: rgba(15, 23, 42, 0.82);
    border-color: rgba(71, 85, 105, 0.3);
  }

  .hero-title {
    color: #e2e8f0;
  }

  .hero-kicker,
  .hero-desc,
  .count {
    color: #94a3b8;
  }
}
</style>
