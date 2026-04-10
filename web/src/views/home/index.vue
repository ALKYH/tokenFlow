<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import SvgIcon from '@/components/custom/svg-icon.vue';
import {
  deleteCloudWorkspace,
  fetchInboxChannels,
  fetchMarketplacePlugins,
  fetchMyCloudWorkspaces,
  fetchMyPluginLibrary,
  fetchMyProfile,
  getStoredAccessToken,
  loadWorkspaceSnapshots,
  parseWorkspaceFile,
  publishWorkspacePlugin,
  savePendingWorkspaceImport,
  saveWorkspaceSnapshot,
  type WorkspaceSnapshot
} from '@/service/api';

const router = useRouter();

const localModules = ref<WorkspaceSnapshot[]>([]);
const cloudModules = ref<any[]>([]);
const cloudWorkspaces = ref<any[]>([]);
const popularModules = ref<any[]>([]);
const inboxChannels = ref<any[]>([]);
const loading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const workspaceQuery = ref('');
const workspaceBusyMap = ref<Record<string, boolean>>({});

const profile = ref({
  name: 'TokenFlow Builder',
  role: 'Visual Pipeline Engineer',
  note: 'Keep modules structured, reusable and easy to debug.',
  email: 'Sign in to sync'
});

const totalNodes = computed(() => localModules.value.reduce((sum, item) => sum + Number(item.stats?.nodes || 0), 0));
const latestModule = computed(() => localModules.value[0] || null);
const token = computed(() => getStoredAccessToken());
const filteredCloudWorkspaces = computed(() => {
  const keyword = workspaceQuery.value.trim().toLowerCase();
  if (!keyword) return cloudWorkspaces.value;
  return cloudWorkspaces.value.filter(item =>
    [item.name, item.description, item.file_type].filter(Boolean).some(part => String(part).toLowerCase().includes(keyword))
  );
});

function formatTime(value?: string) {
  if (!value) return 'N/A';
  try {
    return new Date(value).toLocaleString(undefined, { hour12: false });
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

function workspaceBusyKey(action: string, workspaceId: number | string) {
  return `${action}:${workspaceId}`;
}

function setWorkspaceBusy(action: string, workspaceId: number | string, busy: boolean) {
  const key = workspaceBusyKey(action, workspaceId);
  workspaceBusyMap.value = { ...workspaceBusyMap.value, [key]: busy };
}

function isWorkspaceBusy(action: string, workspaceId: number | string) {
  return !!workspaceBusyMap.value[workspaceBusyKey(action, workspaceId)];
}

function slugify(value: string) {
  return String(value || 'workspace')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || `workspace-${Date.now()}`;
}

function getWorkspaceStats(item: any) {
  const graph = item?.content?.graph || {};
  return {
    nodes: graph?.nodes?.length || 0,
    edges: graph?.edges?.length || 0,
    folders: graph?.folders?.length || 0
  };
}

function exportCloudWorkspace(item: any) {
  const payload = item?.content || {};
  const fileName = `${slugify(item?.name || 'workspace')}-${Date.now()}.json`;
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    try { anchor.remove(); } catch {}
  }, 3000);
}

function viewCloudWorkspace(item: any) {
  const stats = getWorkspaceStats(item);
  window.$dialog?.info({
    title: item.name,
    content: `${item.description || 'No description'}\n\nType: ${item.file_type || 'workspace'}\nNodes: ${stats.nodes}\nEdges: ${stats.edges}\nFolders: ${stats.folders}\nUpdated: ${formatTime(item.updated_at)}`,
    positiveText: 'Close'
  });
}

async function publishCloudWorkspace(item: any) {
  const accessToken = token.value || getStoredAccessToken();
  if (!accessToken) {
    window.$message?.warning('Please sign in before publishing to marketplace');
    return;
  }

  const workspaceId = Number(item.id);
  setWorkspaceBusy('publish', workspaceId, true);
  try {
    const result = await publishWorkspacePlugin(
      {
        workspace_id: workspaceId,
        name: item.name || 'Untitled Workspace',
        slug: `${slugify(item.name || 'workspace')}-${Date.now()}`,
        summary: item.description || 'Published from cloud workspace file',
        category: 'workspace',
        plugin_type: 'module',
        tags: ['workspace', 'creative-market', 'home-dashboard'],
        file_type: item.file_type || 'workspace',
        is_public: true,
        library_kind: 'personal'
      },
      accessToken
    );
    window.$message?.success(`Published: ${result?.name || item.name}`);
  } catch (error: any) {
    window.$message?.error(error?.message || 'Failed to publish');
  } finally {
    setWorkspaceBusy('publish', workspaceId, false);
  }
}

async function removeCloudWorkspace(item: any) {
  const accessToken = token.value || getStoredAccessToken();
  if (!accessToken) {
    window.$message?.warning('Please sign in before deleting cloud files');
    return;
  }

  const workspaceId = Number(item.id);
  window.$dialog?.warning({
    title: 'Delete Cloud File',
    content: `Delete ${item.name}? This cannot be undone.`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      setWorkspaceBusy('delete', workspaceId, true);
      try {
        await deleteCloudWorkspace(workspaceId, accessToken);
        cloudWorkspaces.value = cloudWorkspaces.value.filter(workspace => Number(workspace.id) !== workspaceId);
        window.$message?.success('Cloud file deleted');
      } catch (error: any) {
        window.$message?.error(error?.message || 'Failed to delete cloud file');
      } finally {
        setWorkspaceBusy('delete', workspaceId, false);
      }
    }
  });
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
    window.$message?.success('Module file loaded, opening workspace');
    openBlank({ pending: '1', source: 'file-import' });
  } catch (error: any) {
    window.$message?.error(error?.message || 'Failed to parse module file');
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
      role: 'Personal Library Member',
      note: profileData.bio || 'Connected to profile and cloud module services.',
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

async function refreshCloudWorkspaceFiles() {
  if (!token.value) return;
  try {
    cloudWorkspaces.value = await fetchMyCloudWorkspaces(token.value);
  } catch {
    cloudWorkspaces.value = [];
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
        <h1 class="hero-title">Module Overview And Cloud Sync</h1>
        <p class="hero-desc">
          Review local modules, personal cloud modules, cloud workspaces and inbox channels, and open local module files directly into the editor.
        </p>
        <div class="hero-actions">
          <NButton type="primary" size="large" @click="openBlank()">
            <template #icon><SvgIcon icon="solar:play-circle-linear" /></template>
            Open Workspace
          </NButton>
          <NButton size="large" secondary @click="triggerFileImport">
            <template #icon><SvgIcon icon="solar:upload-linear" /></template>
            Load Local Module File
          </NButton>
          <NButton size="large" tertiary @click="openLocalModule(latestModule?.id)">
            <template #icon><SvgIcon icon="solar:folder-open-linear" /></template>
            Open Latest Module
          </NButton>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="metric-card">
          <div class="metric-label">Local Modules</div>
          <div class="metric-value">{{ localModules.length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Cloud Modules</div>
          <div class="metric-value">{{ cloudModules.length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Total Nodes</div>
          <div class="metric-value">{{ totalNodes }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Inbox Channels</div>
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
                <div class="panel-title">Local Modules</div>
                <div class="panel-subtitle">Resume from browser snapshots or imported files.</div>
              </div>
              <NButton tertiary @click="triggerFileImport">Import File</NButton>
            </div>
          </template>

          <NEmpty v-if="!localModules.length" description="No local modules yet." />
          <div v-else class="card-list">
            <div v-for="item in localModules" :key="item.id" class="module-card" @click="openLocalModule(item.id)">
              <div class="card-head">
                <div>
                  <div class="module-title">{{ item.name }}</div>
                  <div class="module-desc">{{ item.description }}</div>
                </div>
                <NTag round type="info">{{ item.stats.nodes }} nodes</NTag>
              </div>
              <div class="card-meta">
                <span>{{ item.stats.edges }} edges</span>
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
                <div class="panel-title">Personal Module Library</div>
                <div class="panel-subtitle">Cloud modules saved into your personal library.</div>
              </div>
            </div>
          </template>

          <NSpin :show="loading">
            <NEmpty v-if="!cloudModules.length" description="Sign in to load your cloud module library" />
            <div v-else class="card-list">
              <div v-for="item in cloudModules" :key="item.id" class="module-card" @click="openCloudModule(item)">
                <div class="card-head">
                  <div>
                    <div class="module-title">{{ item.name }}</div>
                    <div class="module-desc">{{ item.summary || 'Personal cloud module' }}</div>
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
                <div class="panel-title">Profile</div>
                <div class="panel-subtitle">Sign in to sync modules, node library and inbox channels.</div>
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
                <div class="panel-title">Inbox Channels</div>
                <div class="panel-subtitle">Review channel counts and manage intake methods in Inbox.</div>
              </div>
              <NButton tertiary @click="router.push('/inbox')">Open Inbox</NButton>
            </div>
          </template>

          <NEmpty v-if="!inboxChannels.length" description="No channel stats yet" />
          <div v-else class="card-list">
            <div v-for="item in inboxChannels" :key="item.channel" class="channel-card">
              <div>
                <div class="module-title">{{ item.channel }}</div>
                <div class="module-desc">{{ item.unread }} unread</div>
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
                <div class="panel-title">Popular Modules</div>
                <div class="panel-subtitle">Recommended modules from the marketplace.</div>
              </div>
              <NButton tertiary @click="router.push('/marketplace')">Open Market</NButton>
            </div>
          </template>

          <NEmpty v-if="!popularModules.length" description="No market recommendations yet" />
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
                <div class="panel-title">Cloud Workspace Files</div>
                <div class="panel-subtitle">View and manage cloud files, then publish them to marketplace.</div>
              </div>
              <NButton tertiary @click="refreshCloudWorkspaceFiles">Refresh</NButton>
            </div>
          </template>

          <NInput
            v-model:value="workspaceQuery"
            clearable
            size="small"
            placeholder="Search cloud workspace files"
            style="margin-bottom: 10px;"
          />

          <NEmpty v-if="!filteredCloudWorkspaces.length" description="No cloud workspace files yet" />
          <div v-else class="card-list">
            <div v-for="item in filteredCloudWorkspaces" :key="item.id" class="module-card" @click="openCloudWorkspace(item)">
              <div class="card-head">
                <div>
                  <div class="module-title">{{ item.name }}</div>
                  <div class="module-desc">{{ item.description }}</div>
                </div>
                <NTag round type="primary">{{ item.file_type }}</NTag>
              </div>
              <div class="card-meta">
                <span>ID {{ item.id }} · {{ getWorkspaceStats(item).nodes }} nodes</span>
                <span>{{ formatTime(item.updated_at) }}</span>
              </div>
              <div class="card-actions">
                <NButton size="tiny" secondary @click.stop="viewCloudWorkspace(item)">View</NButton>
                <NButton size="tiny" secondary @click.stop="exportCloudWorkspace(item)">Export</NButton>
                <NButton
                  size="tiny"
                  tertiary
                  type="success"
                  :loading="isWorkspaceBusy('publish', item.id)"
                  @click.stop="publishCloudWorkspace(item)"
                >
                  Publish
                </NButton>
                <NButton
                  size="tiny"
                  tertiary
                  type="error"
                  :loading="isWorkspaceBusy('delete', item.id)"
                  @click.stop="removeCloudWorkspace(item)"
                >
                  Delete
                </NButton>
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

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
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
