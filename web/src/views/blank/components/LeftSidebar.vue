<script setup lang="ts">
import { computed, ref } from 'vue';
import SvgIcon from '@/components/custom/svg-icon.vue';

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
}>();

const searchText = ref('');
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

const nodeStats = computed(() => ({
  categoryCount: (props.categories || []).length,
  localTemplateCount: props.savedNodeTemplates.length,
  cloudModuleCount: props.cloudModuleCount || 0
}));
</script>

<template>
  <aside class="sidebar left" :class="{ collapsed: leftCollapsed }" aria-hidden="false">
    <button class="sidebar-toggle" :title="leftCollapsed ? '展开资源栏' : '收起资源栏'" @click="emit('toggle')">
      {{ leftCollapsed ? '>' : '<' }}
    </button>

    <div v-show="!leftCollapsed" class="sidebar-content">
      <div class="sidebar-header">
        <div>
          <div class="sidebar-kicker">Workspace</div>
          <div class="sidebar-title">节点资源台</div>
        </div>
        <NTag size="small" round type="info">{{ nodeStats.localTemplateCount }} 本地节点</NTag>
      </div>

      <div class="top-actions">
        <NButton type="primary" block @click="emit('savePersonalModule')">
          <template #icon><SvgIcon icon="solar:cloud-upload-linear" /></template>
          保存到个人模块
        </NButton>
      </div>

      <div class="overview-cards">
        <div class="overview-card">
          <div class="overview-label">分类</div>
          <div class="overview-value">{{ nodeStats.categoryCount }}</div>
        </div>
        <div class="overview-card">
          <div class="overview-label">云端模块</div>
          <div class="overview-value">{{ nodeStats.cloudModuleCount }}</div>
        </div>
      </div>

      <NTabs v-model:value="activeTab" type="segment" animated>
        <NTabPane name="library" tab="节点">
          <NInput v-model:value="searchText" clearable placeholder="搜索节点、工具或 LLM 能力" />

          <div class="quick-actions">
            <NButton secondary block @click="emit('addPreset', { key: 'note', label: '注释便签', desc: '记录流程说明与协作备注' })">
              <template #icon><SvgIcon icon="solar:notes-linear" /></template>
              新增便签
            </NButton>
          </div>

          <div class="section-block">
            <div class="section-title">节点库</div>
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

        <NTabPane name="templates" tab="模板">
          <div class="section-block">
            <div class="section-title">工作流模板</div>
            <div class="template-groups">
              <div v-for="group in groupedTemplates" :key="group.key" class="template-group">
                <div class="section-subtitle">{{ group.label }}</div>
                <NEmpty v-if="!group.items.length" size="small" description="暂无模板" />
                <div v-else class="template-list">
                  <div v-for="template in group.items" :key="template.key" class="template-card">
                    <div class="template-head">
                      <div>
                        <div class="template-name">{{ template.label }}</div>
                        <div class="template-desc">{{ template.desc }}</div>
                      </div>
                      <NButton size="small" type="primary" secondary @click="emit('applyWorkflowTemplate', template)">放置</NButton>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="section-block">
            <div class="section-title">本地封装节点</div>
            <NEmpty v-if="!savedNodeTemplates.length" size="small" description="还没有保存到本地的封装节点" />
            <div v-else class="template-list">
              <div v-for="template in savedNodeTemplates" :key="template.id" class="template-card">
                <div class="template-head">
                  <div>
                    <div class="template-name">{{ template.name }}</div>
                    <div class="template-meta">{{ template.version || 'v1.0.0' }} · {{ template.kind || 'local' }}</div>
                  </div>
                  <NDropdown
                    trigger="click"
                    :options="[
                      { label: '添加到画布', key: 'add' },
                      { label: '删除模板', key: 'delete' }
                    ]"
                    @select="key => key === 'add' ? emit('importSavedTemplate', template) : emit('deleteSavedTemplate', template.id)"
                  >
                    <NButton text><SvgIcon icon="solar:menu-dots-linear" /></NButton>
                  </NDropdown>
                </div>
                <div class="template-desc">{{ template.description || '未填写描述' }}</div>
              </div>
            </div>
          </div>
        </NTabPane>

        <NTabPane name="project" tab="项目">
          <div class="section-block">
            <div class="section-title">项目信息</div>
            <NForm label-placement="top" size="small">
              <NFormItem label="项目名称">
                <NInput :value="projectConfig.name" @update:value="value => emit('updateProjectConfig', { field: 'name', value })" />
              </NFormItem>
              <NFormItem label="项目描述">
                <NInput
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                  :value="projectConfig.description"
                  @update:value="value => emit('updateProjectConfig', { field: 'description', value })"
                />
              </NFormItem>
              <NFormItem label="依赖 / 运行时">
                <NInput :value="projectConfig.requires" @update:value="value => emit('updateProjectConfig', { field: 'requires', value })" />
              </NFormItem>
            </NForm>
          </div>

          <div class="section-block">
            <div class="section-title row-between">
              <span>环境变量</span>
              <NButton size="small" secondary @click="emit('addEnvVar')">新增变量</NButton>
            </div>
            <div class="env-list">
              <NEmpty v-if="!envVars.length" size="small" description="尚未配置环境变量" />
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
                  <template #checked>密文</template>
                  <template #unchecked>明文</template>
                </NSwitch>
                <NButton text type="error" @click="emit('removeEnvVar', index)">删除</NButton>
              </div>
            </div>
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

.sidebar.left { left: 8px; }

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

.sidebar-content { display: flex; flex-direction: column; gap: 12px; height: 100%; overflow: auto; }
.sidebar-header, .row-between, .template-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.sidebar-kicker, .overview-label, .library-desc, .template-desc, .template-meta, .section-subtitle { font-size: 12px; color: #64748b; }
.sidebar-title, .overview-value, .library-name, .template-name, .section-title { color: #0f172a; font-weight: 700; }
.sidebar-title { font-size: 18px; }
.top-actions, .template-groups, .template-list, .env-list, .item-grid { display: grid; gap: 10px; }
.overview-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.overview-card, .library-card, .template-card, .env-row { border: 1px solid rgba(148, 163, 184, 0.18); background: rgba(255, 255, 255, 0.78); border-radius: 16px; padding: 12px; }
.library-card { display: grid; grid-template-columns: 14px 1fr; gap: 10px; text-align: left; width: 100%; }
.library-icon { width: 14px; height: 14px; border-radius: 999px; margin-top: 4px; }
.library-main { display: flex; flex-direction: column; gap: 4px; }
.env-row { display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 8px; align-items: center; }

@media (prefers-color-scheme: dark) {
  .sidebar,
  .sidebar-toggle,
  .overview-card,
  .library-card,
  .template-card,
  .env-row {
    background: rgba(15, 23, 42, 0.78);
    border-color: rgba(71, 85, 105, 0.3);
    color: #e2e8f0;
  }

  .sidebar-title,
  .overview-value,
  .library-name,
  .template-name,
  .section-title {
    color: #e2e8f0;
  }

  .sidebar-kicker,
  .overview-label,
  .library-desc,
  .template-desc,
  .template-meta,
  .section-subtitle {
    color: #94a3b8;
  }
}
</style>
