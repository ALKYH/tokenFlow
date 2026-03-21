<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import SvgIcon from '@/components/custom/svg-icon.vue';
import {
  fetchInboxChannels,
  fetchMarketplacePlugins,
  fetchMyCloudWorkspaces,
  fetchMyPluginLibrary,
  fetchMyProfile,
  getStoredAccessToken,
  loadWorkspaceSnapshots,
  parseWorkspaceFile,
  savePendingWorkspaceImport,
  saveWorkspaceSnapshot,
  type WorkspaceSnapshot
} from '@/service/api';
import { getLocale } from '@/locales';

const router = useRouter();
const isZh = computed(() => getLocale() === 'zh-CN');
const localModules = ref<WorkspaceSnapshot[]>([]);
const cloudModules = ref<any[]>([]);
const cloudWorkspaces = ref<any[]>([]);
const popularModules = ref<any[]>([]);
const inboxChannels = ref<any[]>([]);
const loading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

const profile = ref({
  name: 'TokenFlow Builder',
  role: 'Visual Pipeline Engineer',
  note: 'Keep modules structured, reusable and easy to debug.',
  email: 'Sign in to sync'
});

const totalNodes = computed(() => localModules.value.reduce((sum, item) => sum + Number(item.stats?.nodes || 0), 0));
const latestModule = computed(() => localModules.value[0] || null);
const token = computed(() => getStoredAccessToken());

function t(zh: string, en: string) {
  return isZh.value ? zh : en;
}

function formatTime(value?: string) {
  if (!value) return t('未记录', 'N/A');
  try {
    return new Date(value).toLocaleString(isZh.value ? 'zh-CN' : 'en-US', { hour12: false });
  } catch {
    return value;
  }
}

function refreshLocalModules() {
  localModules.value = loadWorkspaceSnapshots().sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
}

function openBlank(query: Record<string, string> = {}) {
  router.push({ path: '/blank', query });
}

function openLocalModule(moduleId?: string) {
  if (!moduleId) return openBlank();
  openBlank({ module: moduleId, source: 'local' });
}

function openCloudModule(item: any) {
  openBlank({ cloudPlugin: String(item.id), source: 'cloud-library' });
}

function openCloudWorkspace(item: any) {
  openBlank({ workspaceId: String(item.id), source: 'cloud-workspace' });
}

function triggerFileImport() {
  fileInputRef.value?.click();
}

async function handleFileImport(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  try {
    const snapshot = await parseWorkspaceFile(file);
    const saved = saveWorkspaceSnapshot({
      ...snapshot,
      meta: { ...(snapshot.meta || {}), source: 'file-import', tags: [...(snapshot.meta?.tags || []), 'file-import'] }
    });
    savePendingWorkspaceImport(saved);
    refreshLocalModules();
    window.$message?.success(t('已读取本地模块文件，正在进入工作区', 'Module file loaded, opening workspace'));
    openBlank({ pending: '1', source: 'file-import' });
  } catch (error: any) {
    window.$message?.error(error?.message || t('模块文件解析失败', 'Failed to parse module file'));
  } finally {
    input.value = '';
  }
}

async function loadData() {
  loading.value = true;
  refreshLocalModules();

  try {
    popularModules.value = (await fetchMarketplacePlugins({ plugin_type: 'module' })).slice(0, 3);
  } catch {
    popularModules.value = [];
  }

  try {
    inboxChannels.value = await fetchInboxChannels(token.value || undefined);
  } catch {
    inboxChannels.value = [];
  }

  if (!token.value) {
    loading.value = false;
    return;
  }

  try {
    const [profileData, libraryData, workspaceData] = await Promise.all([
      fetchMyProfile(token.value),
      fetchMyPluginLibrary({ plugin_type: 'module' }, token.value),
      fetchMyCloudWorkspaces(token.value)
    ]);

    profile.value = {
      name: profileData.display_name || 'TokenFlow User',
      role: t('个人模块库成员', 'Personal Library Member'),
      note: profileData.bio || t('已连接个人资料与云端模块服务', 'Connected to profile and cloud module services.'),
      email: profileData.email || ''
    };
    cloudModules.value = libraryData;
    cloudWorkspaces.value = workspaceData;
  } catch {
    cloudModules.value = [];
    cloudWorkspaces.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="home-dashboard">
    <input ref="fileInputRef" type="file" accept=".json" style="display:none" @change="handleFileImport" />

    <div class="hero-card">
      <div class="hero-copy">
        <div class="hero-kicker">Flow Workspace</div>
        <h1 class="hero-title">{{ t('模块总览与云端同步入口', 'Module Overview And Cloud Sync') }}</h1>
        <p class="hero-desc">
          {{ t('在这里统一查看本地模块、云端个人模块库、云端工作区文件和收件箱渠道，并支持直接读取本地模块文件进入编辑器。', 'Review local modules, personal cloud modules, cloud workspaces and inbox channels, and open local module files directly into the editor.') }}
        </p>
        <div class="hero-actions">
          <NButton type="primary" size="large" @click="openBlank()">
            <template #icon><SvgIcon icon="solar:play-circle-linear" /></template>
            {{ t('进入工作区', 'Open Workspace') }}
          </NButton>
          <NButton size="large" secondary @click="triggerFileImport">
            <template #icon><SvgIcon icon="solar:upload-linear" /></template>
            {{ t('读取本地模块文件', 'Load Local Module File') }}
          </NButton>
          <NButton size="large" tertiary @click="openLocalModule(latestModule?.id)">
            <template #icon><SvgIcon icon="solar:folder-open-linear" /></template>
            {{ t('打开最近模块', 'Open Latest Module') }}
          </NButton>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="metric-card">
          <div class="metric-label">{{ t('本地模块', 'Local Modules') }}</div>
          <div class="metric-value">{{ localModules.length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('云端个人模块', 'Cloud Modules') }}</div>
          <div class="metric-value">{{ cloudModules.length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('累计节点', 'Total Nodes') }}</div>
          <div class="metric-value">{{ totalNodes }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('收件箱渠道', 'Inbox Channels') }}</div>
          <div class="metric-value">{{ inboxChannels.length }}</div>
        </div>
      </div>
    </div>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:12">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('本地模块', 'Local Modules') }}</div>
                <div class="panel-subtitle">{{ t('从浏览器本地快照或导入文件继续进入可视化编辑器', 'Resume from browser snapshots or imported files.') }}</div>
              </div>
              <NButton tertiary @click="triggerFileImport">{{ t('导入文件', 'Import File') }}</NButton>
            </div>
          </template>

          <NEmpty v-if="!localModules.length" :description="t('还没有本地模块，先在工作区创建或导入一个', 'No local modules yet.')" />
          <div v-else class="card-list">
            <div v-for="item in localModules" :key="item.id" class="module-card" @click="openLocalModule(item.id)">
              <div class="card-head">
                <div>
                  <div class="module-title">{{ item.name }}</div>
                  <div class="module-desc">{{ item.description }}</div>
                </div>
                <NTag round type="info">{{ item.stats.nodes }} {{ t('节点', 'nodes') }}</NTag>
              </div>
              <div class="card-meta">
                <span>{{ item.stats.edges }} {{ t('连线', 'edges') }}</span>
                <span>{{ formatTime(item.updatedAt) }}</span>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:12">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('个人模块库', 'Personal Module Library') }}</div>
                <div class="panel-subtitle">{{ t('显示后端保存到个人模块库的云端模块', 'Cloud modules saved into your personal library.') }}</div>
              </div>
            </div>
          </template>

          <NSpin :show="loading">
            <NEmpty v-if="!cloudModules.length" :description="t('未登录或云端模块库为空', 'Sign in to load your cloud module library')" />
            <div v-else class="card-list">
              <div v-for="item in cloudModules" :key="item.id" class="module-card" @click="openCloudModule(item)">
                <div class="card-head">
                  <div>
                    <div class="module-title">{{ item.name }}</div>
                    <div class="module-desc">{{ item.summary || t('个人云端模块', 'Personal cloud module') }}</div>
                  </div>
                  <NTag round type="success">{{ item.plugin_type }}</NTag>
                </div>
                <div class="card-meta">
                  <span>{{ item.category }}</span>
                  <span>{{ formatTime(item.updated_at) }}</span>
                </div>
              </div>
            </div>
          </NSpin>
        </NCard>
      </NGi>
    </NGrid>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:10">
        <NCard :bordered="false" class="panel-card profile-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('个人信息', 'Profile') }}</div>
                <div class="panel-subtitle">{{ t('登录后可同步模块、节点库和消息渠道', 'Sign in to sync modules, node library and inbox channels.') }}</div>
              </div>
            </div>
          </template>
          <div class="profile-body">
            <div class="profile-avatar"><SvgIcon icon="solar:user-circle-linear" /></div>
            <div class="profile-name">{{ profile.name }}</div>
            <div class="profile-role">{{ profile.role }}</div>
            <div class="profile-note">{{ profile.email }}</div>
            <div class="profile-note">{{ profile.note }}</div>
          </div>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:14">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('收件箱渠道', 'Inbox Channels') }}</div>
                <div class="panel-subtitle">{{ t('查看消息渠道数量，并前往收件箱管理接入方式', 'Review channel counts and manage intake methods in Inbox.') }}</div>
              </div>
              <NButton tertiary @click="router.push('/inbox')">{{ t('前往收件箱', 'Open Inbox') }}</NButton>
            </div>
          </template>

          <NEmpty v-if="!inboxChannels.length" :description="t('暂无渠道统计', 'No channel stats yet')" />
          <div v-else class="card-list">
            <div v-for="item in inboxChannels" :key="item.channel" class="channel-card">
              <div>
                <div class="module-title">{{ item.channel }}</div>
                <div class="module-desc">{{ item.unread }} {{ t('未读', 'unread') }}</div>
              </div>
              <NTag round type="warning">{{ item.count }}</NTag>
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:12">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('热门模块', 'Popular Modules') }}</div>
                <div class="panel-subtitle">{{ t('从社区市场推荐较常用的模块模板', 'Recommended modules from the marketplace.') }}</div>
              </div>
              <NButton tertiary @click="router.push('/marketplace')">{{ t('进入市场', 'Open Market') }}</NButton>
            </div>
          </template>

          <NEmpty v-if="!popularModules.length" :description="t('暂无市场推荐', 'No market recommendations yet')" />
          <div v-else class="card-list">
            <div v-for="item in popularModules" :key="item.id" class="module-card" @click="router.push('/marketplace')">
              <div class="card-head">
                <div>
                  <div class="module-title">{{ item.name }}</div>
                  <div class="module-desc">{{ item.summary }}</div>
                </div>
                <NTag round type="success">{{ item.category }}</NTag>
              </div>
              <div class="card-meta">
                <span>{{ item.installs || 0 }} installs</span>
                <span>{{ item.author_name }}</span>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:12">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('云端工作区文件', 'Cloud Workspace Files') }}</div>
                <div class="panel-subtitle">{{ t('读取后端保存的工作区文件并继续编辑', 'Open backend-saved workspace files and continue editing.') }}</div>
              </div>
            </div>
          </template>

          <NEmpty v-if="!cloudWorkspaces.length" :description="t('暂无云端工作区文件', 'No cloud workspace files yet')" />
          <div v-else class="card-list">
            <div v-for="item in cloudWorkspaces" :key="item.id" class="module-card" @click="openCloudWorkspace(item)">
              <div class="card-head">
                <div>
                  <div class="module-title">{{ item.name }}</div>
                  <div class="module-desc">{{ item.description }}</div>
                </div>
                <NTag round type="primary">{{ item.file_type }}</NTag>
              </div>
              <div class="card-meta">
                <span>ID {{ item.id }}</span>
                <span>{{ formatTime(item.updated_at) }}</span>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped>
.home-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card {
  display: grid;
  grid-template-columns: 1.3fr .9fr;
  gap: 16px;
  padding: 24px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.18), transparent 34%),
    radial-gradient(circle at bottom right, rgba(14, 165, 233, 0.14), transparent 30%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
}

.hero-kicker,
.hero-desc,
.metric-label,
.card-meta,
.profile-role,
.profile-note,
.panel-subtitle {
  font-size: 12px;
  color: #64748b;
}

.hero-title,
.panel-title,
.module-title,
.profile-name {
  color: #0f172a;
  font-weight: 700;
}

.hero-title {
  margin: 8px 0 10px;
  font-size: 32px;
}

.hero-desc,
.module-desc {
  color: #475569;
  line-height: 1.65;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}

.hero-metrics,
.card-list {
  display: grid;
  gap: 12px;
}

.metric-card,
.module-card,
.channel-card {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.82);
  border-radius: 20px;
  padding: 16px;
}

.metric-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.panel-card {
  border-radius: 24px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.06);
}

.panel-header,
.card-head,
.card-meta,
.channel-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-head {
  align-items: flex-start;
}

.module-card {
  cursor: pointer;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}

.module-card:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.24);
  box-shadow: 0 16px 30px rgba(37, 99, 235, 0.08);
}

.profile-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 12px;
  padding: 12px 8px 4px;
}

.profile-avatar {
  display: grid;
  place-items: center;
  width: 76px;
  height: 76px;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(14, 165, 233, 0.12));
  color: #1d4ed8;
  font-size: 34px;
}

@media (max-width: 1024px) {
  .hero-card {
    grid-template-columns: 1fr;
  }
}

@media (prefers-color-scheme: dark) {
  .hero-card,
  .metric-card,
  .module-card,
  .channel-card {
    background: rgba(15, 23, 42, 0.82);
    border-color: rgba(71, 85, 105, 0.3);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.22);
  }

  .hero-title,
  .panel-title,
  .module-title,
  .metric-value,
  .profile-name {
    color: #e2e8f0;
  }

  .hero-kicker,
  .hero-desc,
  .metric-label,
  .card-meta,
  .profile-role,
  .profile-note,
  .module-desc,
  .panel-subtitle {
    color: #94a3b8;
  }

  .profile-avatar {
    background: rgba(59, 130, 246, 0.16);
    color: #93c5fd;
  }
}
</style>
