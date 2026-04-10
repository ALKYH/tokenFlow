<script setup lang="ts">
import { computed, ref } from 'vue';
import SvgIcon from '@/components/custom/svg-icon.vue';

type CloudWorkspaceItem = {
  id: number;
  name: string;
  description?: string;
  file_type?: string;
  updated_at?: string;
  content?: Record<string, any>;
};

const props = defineProps<{
  categories: any[]
  leftCollapsed: boolean
  nodeCategoryColor: (s?: string) => string
  projectConfig: { name: string; description: string; requires: string }
  envVars: Array<{ key: string; value: string; secret?: boolean }>
  savedNodeTemplates: any[]
  workflowTemplates: any[]
  workflowTemplateGroups: Array<{ key: string; label: string }>
  cloudModuleCount?: number
  cloudWorkspaces?: CloudWorkspaceItem[]
  activeCloudWorkspaceId?: number | null
  cloudWorkspacesLoading?: boolean
}>();

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'addPreset', payload: any): void
  (e: 'applyWorkflowTemplate', payload: any): void
  (e: 'updateProjectConfig', payload: { field: 'name' | 'description' | 'requires'; value: string }): void
  (e: 'addEnvVar'): void
  (e: 'removeEnvVar', index: number): void
  (e: 'updateEnvVar', payload: { index: number; field: 'key' | 'value' | 'secret'; value: string | boolean }): void
  (e: 'importSavedTemplate', payload: any): void
  (e: 'deleteSavedTemplate', payload: string): void
  (e: 'savePersonalModule'): void
  (e: 'saveCloudWorkspace'): void
  (e: 'refreshCloudWorkspaces'): void
  (e: 'openCloudWorkspace', workspaceId: number): void
  (e: 'deleteCloudWorkspace', workspaceId: number): void
  (e: 'publishWorkspace', workspaceId?: number): void
  (e: 'importWorkspaceJson'): void
  (e: 'exportWorkspaceJson'): void
}>();

const searchText = ref('');
const cloudSearch = ref('');
const activeTab = ref<'library' | 'templates' | 'project'>('library');

const filteredCategories = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  if (!keyword) return props.categories || [];
  return (props.categories || [])
    .map(category => ({
      ...category,
      items: (category.items || []).filter((item: any) =>
        [item.label, item.desc, item.key].filter(Boolean).some((part: string) => String(part).toLowerCase().includes(keyword))
      )
    }))
    .filter(category => category.items.length > 0);
});

const groupedTemplates = computed(() =>
  (props.workflowTemplateGroups || []).map(group => ({
    ...group,
    items: (props.workflowTemplates || []).filter(item => item.group === group.key)
  }))
);

const filteredCloudWorkspaces = computed(() => {
  const keyword = cloudSearch.value.trim().toLowerCase();
  if (!keyword) return props.cloudWorkspaces || [];
  return (props.cloudWorkspaces || []).filter(item =>
    [item.name, item.description, item.file_type].filter(Boolean).some(part => String(part).toLowerCase().includes(keyword))
  );
});

const nodeStats = computed(() => ({
  categoryCount: (props.categories || []).length,
  localTemplateCount: props.savedNodeTemplates.length,
  cloudModuleCount: props.cloudModuleCount || 0,
  cloudWorkspaceCount: (props.cloudWorkspaces || []).length
}));

function formatTime(value?: string) {
  if (!value) return 'N/A';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function getWorkspaceNodeCount(item: CloudWorkspaceItem) {
  return item?.content?.graph?.nodes?.length || item?.content?.nodes?.length || 0;
}
</script>

<template>
  <aside class="sidebar left" :class="{ collapsed: leftCollapsed }" aria-hidden="false">
    <button class="sidebar-toggle" :title="leftCollapsed ? 'Expand resources' : 'Collapse resources'" @click="emit('toggle')">
      {{ leftCollapsed ? '>' : '<' }}
    </button>

    <div v-show="!leftCollapsed" class="sidebar-content">
      <div class="sidebar-header">
        <div>
          <div class="sidebar-kicker">Workspace</div>
          <div class="sidebar-title">Node Resources</div>
        </div>
        <NTag size="small" round type="info">{{ nodeStats.localTemplateCount }} local templates</NTag>
      </div>

      <div class="top-actions">
        <NButton type="primary" block @click="emit('savePersonalModule')">
          <template #icon><SvgIcon icon="solar:cloud-upload-linear" /></template>
          Save As Personal Module
        </NButton>
        <NButton secondary block @click="emit('saveCloudWorkspace')">
          <template #icon><SvgIcon icon="solar:diskette-linear" /></template>
          Save Cloud Workspace File
        </NButton>
        <NButton tertiary block @click="emit('publishWorkspace')">
          <template #icon><SvgIcon icon="solar:global-linear" /></template>
          Publish To Creative Market
        </NButton>
      </div>

      <div class="overview-cards">
        <div class="overview-card">
          <div class="overview-label">Categories</div>
          <div class="overview-value">{{ nodeStats.categoryCount }}</div>
        </div>
        <div class="overview-card">
          <div class="overview-label">Cloud Modules</div>
          <div class="overview-value">{{ nodeStats.cloudModuleCount }}</div>
        </div>
        <div class="overview-card">
          <div class="overview-label">Cloud Files</div>
          <div class="overview-value">{{ nodeStats.cloudWorkspaceCount }}</div>
        </div>
        <div class="overview-card">
          <div class="overview-label">Local Templates</div>
          <div class="overview-value">{{ nodeStats.localTemplateCount }}</div>
        </div>
      </div>

      <NTabs v-model:value="activeTab" type="segment" animated>
        <NTabPane name="library" tab="Nodes">
          <NInput v-model:value="searchText" clearable placeholder="Search nodes, tools or capabilities" />

          <div class="quick-actions">
            <NButton secondary block @click="emit('addPreset', { key: 'note', label: 'Sticky Note', desc: 'Add comments to your graph' })">
              <template #icon><SvgIcon icon="solar:notes-linear" /></template>
              Add Sticky Note
            </NButton>
          </div>

          <div class="section-block">
            <div class="section-title">Node Library</div>
            <NCollapse :default-expanded-names="filteredCategories.map((item: any) => item.key)">
              <NCollapseItem v-for="cat in filteredCategories" :key="cat.key" :title="cat.label" :name="cat.key">
                <div class="item-grid">
                  <button v-for="item in cat.items" :key="item.key" class="library-card" @click="emit('addPreset', item)">
                    <span class="library-icon" :style="{ background: nodeCategoryColor(item.key) }"></span>
                    <span class="library-main">
                      <span class="library-name">{{ item.label }}</span>
                      <span class="library-desc">{{ item.desc }}</span>
                    </span>
                  </button>
                </div>
              </NCollapseItem>
            </NCollapse>
          </div>
        </NTabPane>

        <NTabPane name="templates" tab="Templates">
          <div class="section-block">
            <div class="section-title">Workflow Templates</div>
            <div class="template-groups">
              <div v-for="group in groupedTemplates" :key="group.key" class="template-group">
                <div class="section-subtitle">{{ group.label }}</div>
                <NEmpty v-if="!group.items.length" size="small" description="No templates yet" />
                <div v-else class="template-list">
                  <div v-for="template in group.items" :key="template.key" class="template-card">
                    <div class="template-head">
                      <div>
                        <div class="template-name">{{ template.label }}</div>
                        <div class="template-desc">{{ template.desc }}</div>
                      </div>
                      <NButton size="small" type="primary" secondary @click="emit('applyWorkflowTemplate', template)">Insert</NButton>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="section-block">
            <div class="section-title">Local Node Templates</div>
            <NEmpty v-if="!savedNodeTemplates.length" size="small" description="No local templates yet" />
            <div v-else class="template-list">
              <div v-for="template in savedNodeTemplates" :key="template.id" class="template-card">
                <div class="template-head">
                  <div>
                    <div class="template-name">{{ template.name }}</div>
                    <div class="template-meta">{{ template.version || 'v1.0.0' }} | {{ template.kind || 'local' }}</div>
                  </div>
                  <NDropdown
                    trigger="click"
                    :options="[
                      { label: 'Add To Canvas', key: 'add' },
                      { label: 'Delete Template', key: 'delete' }
                    ]"
                    @select="key => key === 'add' ? emit('importSavedTemplate', template) : emit('deleteSavedTemplate', template.id)"
                  >
                    <NButton text><SvgIcon icon='solar:menu-dots-linear' /></NButton>
                  </NDropdown>
                </div>
                <div class="template-desc">{{ template.description || 'No description' }}</div>
              </div>
            </div>
          </div>
        </NTabPane>

        <NTabPane name="project" tab="Project">
          <div class="section-block">
            <div class="section-title">Project Metadata</div>
            <NForm label-placement="top" size="small">
              <NFormItem label="Project Name">
                <NInput :value="projectConfig.name" @update:value="value => emit('updateProjectConfig', { field: 'name', value })" />
              </NFormItem>
              <NFormItem label="Description">
                <NInput
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                  :value="projectConfig.description"
                  @update:value="value => emit('updateProjectConfig', { field: 'description', value })"
                />
              </NFormItem>
              <NFormItem label="Runtime Requires">
                <NInput :value="projectConfig.requires" @update:value="value => emit('updateProjectConfig', { field: 'requires', value })" />
              </NFormItem>
            </NForm>
          </div>

          <div class="section-block">
            <div class="section-title row-between">
              <span>Environment Variables</span>
              <NButton size="small" secondary @click="emit('addEnvVar')">Add Variable</NButton>
            </div>
            <div class="env-list">
              <NEmpty v-if="!envVars.length" size="small" description="No environment variables" />
              <div v-for="(env, index) in envVars" :key="`${env.key}-${index}`" class="env-row">
                <NInput size="small" placeholder="KEY" :value="env.key" @update:value="value => emit('updateEnvVar', { index, field: 'key', value })" />
                <NInput
                  size="small"
                  placeholder="Value"
                  :type="env.secret ? 'password' : 'text'"
                  show-password-on="click"
                  :value="env.value"
                  @update:value="value => emit('updateEnvVar', { index, field: 'value', value })"
                />
                <NSwitch size="small" :value="!!env.secret" @update:value="value => emit('updateEnvVar', { index, field: 'secret', value })">
                  <template #checked>Secret</template>
                  <template #unchecked>Plain</template>
                </NSwitch>
                <NButton text type="error" @click="emit('removeEnvVar', index)">Delete</NButton>
              </div>
            </div>
          </div>

          <div class="section-block">
            <div class="section-title row-between">
              <span>Cloud Workspace Files</span>
              <NButton size="small" tertiary @click="emit('refreshCloudWorkspaces')">
                <template #icon><SvgIcon icon="solar:refresh-linear" /></template>
                Refresh
              </NButton>
            </div>
            <NInput v-model:value="cloudSearch" clearable placeholder="Search cloud workspace files" />

            <div class="workspace-actions">
              <NButton size="small" secondary @click="emit('importWorkspaceJson')">
                <template #icon><SvgIcon icon="solar:upload-linear" /></template>
                Import JSON
              </NButton>
              <NButton size="small" secondary @click="emit('exportWorkspaceJson')">
                <template #icon><SvgIcon icon="solar:download-linear" /></template>
                Export JSON
              </NButton>
            </div>

            <NSpin :show="!!cloudWorkspacesLoading">
              <NEmpty v-if="!filteredCloudWorkspaces.length" size="small" description="No cloud workspace files" />
              <div v-else class="workspace-list">
                <div
                  v-for="item in filteredCloudWorkspaces"
                  :key="item.id"
                  class="workspace-card"
                  :class="{ active: activeCloudWorkspaceId === item.id }"
                  @click="emit('openCloudWorkspace', item.id)"
                >
                  <div class="workspace-head">
                    <div class="workspace-name">{{ item.name }}</div>
                    <NTag size="small" type="info" round>{{ item.file_type || 'workspace' }}</NTag>
                  </div>
                  <div class="workspace-desc">{{ item.description || 'No description' }}</div>
                  <div class="workspace-meta">
                    <span>{{ getWorkspaceNodeCount(item) }} nodes</span>
                    <span>{{ formatTime(item.updated_at) }}</span>
                  </div>
                  <div class="workspace-buttons">
                    <NButton size="tiny" secondary @click.stop="emit('openCloudWorkspace', item.id)">Open</NButton>
                    <NButton size="tiny" tertiary type="success" @click.stop="emit('publishWorkspace', item.id)">Publish</NButton>
                    <NButton size="tiny" tertiary type="error" @click.stop="emit('deleteCloudWorkspace', item.id)">Delete</NButton>
                  </div>
                </div>
              </div>
            </NSpin>
          </div>
        </NTabPane>
      </NTabs>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 320px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.9));
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  padding: 14px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(18px);
  position: absolute;
  top: 80px;
  bottom: 8px;
  z-index: 2500;
  overflow: visible;
}

.sidebar.left {
  left: 8px;
}

.sidebar-toggle {
  cursor: pointer;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.9);
  color: #334155;
  position: absolute;
  top: 26px;
  right: -18px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.12);
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow: auto;
}

.sidebar-header,
.row-between,
.template-head,
.workspace-head,
.workspace-meta,
.workspace-buttons {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sidebar-header,
.template-head,
.workspace-head {
  align-items: flex-start;
}

.sidebar-kicker,
.overview-label,
.library-desc,
.template-desc,
.template-meta,
.section-subtitle,
.workspace-desc,
.workspace-meta {
  font-size: 12px;
  color: #64748b;
}

.sidebar-title,
.overview-value,
.library-name,
.template-name,
.section-title,
.workspace-name {
  color: #0f172a;
  font-weight: 700;
}

.sidebar-title {
  font-size: 18px;
}

.top-actions,
.template-groups,
.template-list,
.env-list,
.item-grid,
.workspace-list {
  display: grid;
  gap: 10px;
}

.workspace-actions {
  display: flex;
  gap: 8px;
}

.overview-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.overview-card,
.library-card,
.template-card,
.env-row,
.workspace-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.78);
  border-radius: 16px;
  padding: 12px;
}

.workspace-card {
  cursor: pointer;
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}

.workspace-card:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.workspace-card.active {
  border-color: rgba(37, 99, 235, 0.44);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.library-card {
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: 10px;
  text-align: left;
  width: 100%;
}

.library-icon {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  margin-top: 4px;
}

.library-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.env-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto;
  gap: 8px;
  align-items: center;
}

@media (prefers-color-scheme: dark) {
  .sidebar,
  .sidebar-toggle,
  .overview-card,
  .library-card,
  .template-card,
  .env-row,
  .workspace-card {
    background: rgba(15, 23, 42, 0.78);
    border-color: rgba(71, 85, 105, 0.3);
    color: #e2e8f0;
  }

  .sidebar-title,
  .overview-value,
  .library-name,
  .template-name,
  .section-title,
  .workspace-name {
    color: #e2e8f0;
  }

  .sidebar-kicker,
  .overview-label,
  .library-desc,
  .template-desc,
  .template-meta,
  .section-subtitle,
  .workspace-desc,
  .workspace-meta {
    color: #94a3b8;
  }
}
</style>
