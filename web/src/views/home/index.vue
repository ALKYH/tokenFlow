<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import SvgIcon from '@/components/custom/svg-icon.vue';
import {
  fetchMarketplacePlugins,
  fetchMyCloudWorkspaces,
  fetchMyProfile,
  getStoredAccessToken
} from '@/service/api';
import { getLocale } from '@/locales';

type WorkspaceSnapshot = {
  name?: string;
  description?: string;
  nodeCount?: number;
  edgeCount?: number;
  updatedAt?: string;
  id?: string;
};

const router = useRouter();
const isZh = computed(() => getLocale() === 'zh-CN');
const modules = ref<WorkspaceSnapshot[]>([]);
const cloudWorkspaces = ref<any[]>([]);
const popularModules = ref<any[]>([]);
const profile = ref({
  name: 'TokenFlow Builder',
  role: 'Visual Pipeline Engineer',
  note: 'Keep modules structured, reusable and easy to debug.',
  email: 'Sign in to sync'
});

const inboxMessages = computed(() => [
  {
    title: isZh.value ? '知识库索引已空闲' : 'Knowledge indexing is idle',
    detail: isZh.value ? '最近一轮 PDF 入库任务已完成，可继续追加文件。' : 'The latest PDF ingestion run completed successfully.',
    time: isZh.value ? '刚刚' : 'Just now',
    tone: 'success'
  },
  {
    title: isZh.value ? '第三方包调试提醒' : 'Package debug reminder',
    detail: isZh.value ? '如果代码模块运行失败，请先检查工具台中的安装日志。' : 'Check the tool panel install logs when Python packages fail.',
    time: isZh.value ? '10 分钟前' : '10 min ago',
    tone: 'warning'
  },
  {
    title: isZh.value ? '社区市场已同步' : 'Marketplace synced',
    detail: isZh.value ? '热门模块推荐会优先展示社区内下载量更高的工作流。' : 'Popular module cards are ranked from marketplace installs.',
    time: isZh.value ? '今天' : 'Today',
    tone: 'info'
  }
]);

const routeStatus = computed(() => [
  {
    label: isZh.value ? '模块工作区' : 'Workspace',
    value: isZh.value ? '正常' : 'Healthy',
    desc: isZh.value ? '节点编辑器与工具台可直接进入' : 'Editor and tool panel are available',
    icon: 'solar:widget-3-linear',
    tone: 'success'
  },
  {
    label: isZh.value ? '知识库链路' : 'Knowledge Flow',
    value: isZh.value ? '在线' : 'Online',
    desc: isZh.value ? 'PDF 解析、分块、Embedding 与检索节点可见' : 'Parsing, chunking and retrieval nodes are visible',
    icon: 'solar:database-linear',
    tone: 'info'
  },
  {
    label: isZh.value ? '社区市场' : 'Marketplace',
    value: isZh.value ? '可用' : 'Ready',
    desc: isZh.value ? '支持将市场模块导入个人模块库' : 'Supports importing market modules into local library',
    icon: 'solar:shop-linear',
    tone: 'warning'
  }
]);

const totalNodes = computed(() => modules.value.reduce((sum, item) => sum + (item.nodeCount || 0), 0));
const latestModule = computed(() => modules.value[0] || null);
const cloudCount = computed(() => cloudWorkspaces.value.length);

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

function openWorkspace() {
  router.push('/blank');
}

function openModule(moduleId?: string) {
  router.push({ path: '/blank', query: moduleId ? { module: moduleId } : {} });
}

onMounted(async () => {
  try {
    const raw = localStorage.getItem('tokenflow.workspace.modules.v1');
    const parsed = raw ? JSON.parse(raw) : [];
    const list = Array.isArray(parsed?.modules) ? parsed.modules : Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
    modules.value = list
      .map((item: any, index: number) => ({
        id: item.id || `workspace-${index + 1}`,
        name: item.name || `Workspace ${index + 1}`,
        description: item.description || t('可视化工作区模块', 'Visual workspace module'),
        nodeCount: item.stats?.nodes || item.nodeCount || item.nodes?.length || 0,
        edgeCount: item.stats?.edges || item.edgeCount || item.edges?.length || 0,
        updatedAt: item.updatedAt || item.savedAt || ''
      }))
      .sort((a: WorkspaceSnapshot, b: WorkspaceSnapshot) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
  } catch {
    modules.value = [];
  }

  try {
    const market = await fetchMarketplacePlugins();
    popularModules.value = market.slice(0, 3);
  } catch {
    popularModules.value = [];
  }

  const token = getStoredAccessToken();
  if (!token) return;

  fetchMyProfile(token)
    .then(data => {
      profile.value = {
        name: data.display_name || 'TokenFlow User',
        role: t('云端工作区成员', 'Cloud Workspace Member'),
        note: data.bio || t('已连接到个人资料服务。', 'Connected to profile service.'),
        email: data.email || ''
      };
    })
    .catch(() => {});

  fetchMyCloudWorkspaces(token)
    .then(data => {
      cloudWorkspaces.value = data;
    })
    .catch(() => {});
});
</script>

<template>
  <div class="home-dashboard">
    <div class="hero-card">
      <div class="hero-copy">
        <div class="hero-kicker">Flow Workspace</div>
        <h1 class="hero-title">{{ t('模块总览与工作台入口', 'Workspace Overview And Entry') }}</h1>
        <p class="hero-desc">
          {{ t('统一查看本地模块、市场推荐、路由状态与云端文件，并从这里继续进入节点工作区。', 'Review local modules, market picks, routing status and cloud files, then jump back into the node editor.') }}
        </p>
        <div class="hero-actions">
          <NButton type="primary" size="large" @click="openWorkspace">
            <template #icon>
              <SvgIcon icon="solar:play-circle-linear" />
            </template>
            {{ t('进入工作区', 'Open Workspace') }}
          </NButton>
          <NButton size="large" secondary @click="openModule(latestModule?.id)">
            <template #icon>
              <SvgIcon icon="solar:folder-open-linear" />
            </template>
            {{ t('打开最近模块', 'Open Latest Module') }}
          </NButton>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="metric-card">
          <div class="metric-label">{{ t('本地模块', 'Local Modules') }}</div>
          <div class="metric-value">{{ modules.length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('累计节点', 'Total Nodes') }}</div>
          <div class="metric-value">{{ totalNodes }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('最近更新', 'Last Updated') }}</div>
          <div class="metric-value metric-sm">{{ formatTime(latestModule?.updatedAt) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">{{ t('云端文件', 'Cloud Files') }}</div>
          <div class="metric-value">{{ cloudCount }}</div>
        </div>
      </div>
    </div>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:16">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('模块管理', 'Module Management') }}</div>
                <div class="panel-subtitle">{{ t('管理本地多个模块，点击即可进入工作区查看内部节点', 'Browse local workspace projects and jump into the editor.') }}</div>
              </div>
              <NButton tertiary @click="openWorkspace">{{ t('查看全部', 'View All') }}</NButton>
            </div>
          </template>

          <NEmpty v-if="!modules.length" :description="t('还没有本地模块快照，先进入工作区创建模块吧', 'No local workspace snapshots yet.')" />

          <div v-else class="module-list">
            <div v-for="item in modules" :key="item.id" class="module-card" @click="openModule(item.id)">
              <div class="module-card-head">
                <div>
                  <div class="module-card-title">{{ item.name }}</div>
                  <div class="module-card-desc">{{ item.description }}</div>
                </div>
                <NTag round type="info">{{ item.nodeCount || 0 }} {{ t('节点', 'nodes') }}</NTag>
              </div>
              <div class="module-card-meta">
                <span>{{ item.edgeCount || 0 }} {{ t('连线', 'edges') }}</span>
                <span>{{ formatTime(item.updatedAt) }}</span>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:8">
        <NCard :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">{{ t('最新消息', 'Latest Messages') }}</div>
                <div class="panel-subtitle">{{ t('编辑提醒、调试建议与市场更新', 'Editor reminders, debug tips and market updates') }}</div>
              </div>
            </div>
          </template>

          <div class="inbox-list">
            <div v-for="item in inboxMessages" :key="item.title" class="inbox-item" :class="item.tone">
              <div class="inbox-title">{{ item.title }}</div>
              <div class="inbox-detail">{{ item.detail }}</div>
              <div class="inbox-time">{{ item.time }}</div>
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
                <div class="panel-title">{{ t('热门市场模块', 'Popular Market Modules') }}</div>
                <div class="panel-subtitle">{{ t('从社区市场中推荐下载量和安装量更高的模块', 'Top modules from the community marketplace') }}</div>
              </div>
              <NButton tertiary @click="router.push('/marketplace')">{{ t('进入市场', 'Open Market') }}</NButton>
            </div>
          </template>

          <NEmpty v-if="!popularModules.length" :description="t('暂时没有可展示的市场推荐', 'No market recommendations yet')" />
          <div v-else class="module-list">
            <div v-for="item in popularModules" :key="item.id" class="module-card" @click="router.push('/marketplace')">
              <div class="module-card-head">
                <div>
                  <div class="module-card-title">{{ item.name }}</div>
                  <div class="module-card-desc">{{ item.summary }}</div>
                </div>
                <NTag round type="success">{{ item.category }}</NTag>
              </div>
              <div class="module-card-meta">
                <span>{{ item.installs || 0 }} installs</span>
                <span>{{ item.author_name || 'TokenFlow' }}</span>
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
                <div class="panel-title">{{ t('路由工作情况', 'Routing Status') }}</div>
                <div class="panel-subtitle">{{ t('查看工作区、知识库和社区市场链路状态', 'Track workspace, knowledge and market flows') }}</div>
              </div>
            </div>
          </template>

          <div class="route-list">
            <div v-for="item in routeStatus" :key="item.label" class="route-card">
              <div class="route-icon">
                <SvgIcon :icon="item.icon" />
              </div>
              <div class="route-copy">
                <div class="route-title">{{ item.label }}</div>
                <div class="route-desc">{{ item.desc }}</div>
              </div>
              <NTag round :type="item.tone as any">{{ item.value }}</NTag>
            </div>
          </div>
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
                <div class="panel-subtitle">{{ t('点击顶部头像可修改个人偏好和云端 API Key', 'Use the top avatar modal to edit preferences and cloud API keys') }}</div>
              </div>
            </div>
          </template>

          <div class="profile-body">
            <div class="profile-avatar">
              <SvgIcon icon="solar:user-circle-linear" />
            </div>
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
                <div class="panel-title">{{ t('云端工作文件', 'Cloud Workspace Files') }}</div>
                <div class="panel-subtitle">{{ t('登录后可读取 PostgreSQL 中保存的工作区快照', 'Workspace snapshots stored in PostgreSQL') }}</div>
              </div>
            </div>
          </template>

          <NEmpty v-if="!cloudWorkspaces.length" :description="t('当前没有云端工作文件，或尚未连接到后端账号', 'No cloud files yet or backend login is not active')" />
          <div v-else class="module-list">
            <div v-for="item in cloudWorkspaces" :key="item.id" class="module-card">
              <div class="module-card-head">
                <div>
                  <div class="module-card-title">{{ item.name }}</div>
                  <div class="module-card-desc">{{ item.description }}</div>
                </div>
                <NTag round type="success">{{ item.file_type }}</NTag>
              </div>
              <div class="module-card-meta">
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
  grid-template-columns: 1.4fr .9fr;
  gap: 16px;
  padding: 24px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.18), transparent 34%),
    radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.16), transparent 28%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
}

.hero-kicker,
.panel-subtitle,
.metric-label,
.module-card-meta,
.inbox-time,
.profile-role {
  font-size: 12px;
  color: #64748b;
}

.hero-title,
.panel-title,
.module-card-title,
.route-title,
.profile-name {
  color: #0f172a;
  font-weight: 700;
}

.hero-title {
  margin: 8px 0 10px;
  font-size: 32px;
  line-height: 1.15;
}

.hero-desc,
.module-card-desc,
.inbox-detail,
.route-desc,
.profile-note {
  color: #475569;
  line-height: 1.65;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}

.hero-metrics {
  display: grid;
  gap: 12px;
}

.metric-card,
.module-card,
.inbox-item,
.route-card {
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

.metric-sm {
  font-size: 15px;
  line-height: 1.5;
}

.panel-card {
  border-radius: 24px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.06);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.module-list,
.inbox-list,
.route-list {
  display: grid;
  gap: 12px;
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

.module-card-head,
.module-card-meta,
.route-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.module-card-head {
  align-items: flex-start;
}

.inbox-item.success {
  background: rgba(240, 253, 244, 0.9);
}

.inbox-item.warning {
  background: rgba(255, 251, 235, 0.92);
}

.inbox-item.info {
  background: rgba(239, 246, 255, 0.9);
}

.inbox-title {
  font-weight: 700;
  color: #0f172a;
}

.inbox-time {
  margin-top: 8px;
}

.route-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
}

.route-copy {
  flex: 1;
}

.profile-card {
  height: 100%;
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
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(16, 185, 129, 0.12));
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
  .inbox-item,
  .route-card {
    background: rgba(15, 23, 42, 0.8);
    border-color: rgba(71, 85, 105, 0.3);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.22);
  }

  .hero-title,
  .panel-title,
  .module-card-title,
  .route-title,
  .profile-name,
  .metric-value,
  .inbox-title {
    color: #e2e8f0;
  }

  .hero-kicker,
  .panel-subtitle,
  .metric-label,
  .module-card-meta,
  .inbox-time,
  .profile-role,
  .hero-desc,
  .module-card-desc,
  .inbox-detail,
  .route-desc,
  .profile-note {
    color: #94a3b8;
  }

  .route-icon,
  .profile-avatar {
    background: rgba(59, 130, 246, 0.16);
    color: #93c5fd;
  }
}
</style>
