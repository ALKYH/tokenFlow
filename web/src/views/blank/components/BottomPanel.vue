<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import SvgIcon from '@/components/custom/svg-icon.vue';

const props = defineProps<{
  bottomCollapsed: boolean
  modulePaths: string[]
  modulesData: Record<string, any>
  selectedModule: string
  leftCollapsed?: boolean
  rightCollapsed?: boolean
  logs: string[]
  envVars: Array<{ key: string; value: string; secret?: boolean }>
  watchItems: Array<{ id: string; label: string; status?: string; value: any }>
  nodeEvents?: Array<{
    id: string
    run_id: string
    node_id: string
    node_label: string
    mode: string
    phase: string
    status: string
    detail?: string
    duration_ms?: number
    ts: string
  }>
  activeRunId?: string
}>();

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'load', id: string): void
  (e: 'scroll', id: string): void
  (e: 'saveModule', payload: { id: string; source: string }): void
}>();

const moduleSource = ref('');

watch(
  () => props.selectedModule,
  value => {
    moduleSource.value = props.modulesData?.[value]?.source || '';
  },
  { immediate: true }
);

watch(
  () => props.modulesData,
  () => {
    moduleSource.value = props.modulesData?.[props.selectedModule]?.source || '';
  }
);

const SIDEBAR_OFFSET = 8 + 320 + 8;

const panelStyle = computed(() => {
  const left = props.leftCollapsed ? 0 : SIDEBAR_OFFSET;
  const right = props.rightCollapsed ? 0 : SIDEBAR_OFFSET;
  return { left: `${left}px`, right: `${right}px` };
});

const logRows = computed(() =>
  (props.logs || []).map((message, index) => {
    const text = String(message || '');
    const lower = text.toLowerCase();
    let level: 'error' | 'warning' | 'success' | 'info' = 'info';
    if (lower.includes('error') || lower.includes('traceback') || lower.includes('exception') || lower.includes('stderr')) level = 'error';
    else if (lower.includes('warning') || lower.includes('warn')) level = 'warning';
    else if (lower.includes('done') || lower.includes('success') || lower.includes('ready')) level = 'success';
    return { id: `${index}-${text.slice(0, 12)}`, text, level };
  })
);

const latestErrorLog = computed(() => logRows.value.find(item => item.level === 'error') || null);
const errorCount = computed(() => logRows.value.filter(item => item.level === 'error').length);

const nodeEventRows = computed(() => props.nodeEvents || []);
const activeNodeEvents = computed(() => {
  if (!props.activeRunId) return nodeEventRows.value.slice(0, 120);
  return nodeEventRows.value.filter(item => item.run_id === props.activeRunId).slice(0, 120);
});
const nodeEventErrorCount = computed(() => activeNodeEvents.value.filter(item => item.status === 'error').length);

function formatEventTime(ts: string) {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  return date.toLocaleTimeString();
}

function formatWatchValue(value: any) {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
</script>

<template>
  <div class="bottom-panel" :class="{ collapsed: bottomCollapsed }" :style="panelStyle">
    <div class="bottom-panel-handle" @click="emit('toggle')">
      <SvgIcon :icon="bottomCollapsed ? 'solar:alt-arrow-up-linear' : 'solar:alt-arrow-down-linear'" />
      <span>{{ bottomCollapsed ? 'Expand Tools' : 'Collapse Tools' }}</span>
    </div>

    <div v-show="!bottomCollapsed" class="bottom-panel-body">
      <div class="panel-summary">
        <div class="summary-card">
          <div class="summary-kicker">Debug Overview</div>
          <div class="summary-value">{{ logRows.length }}</div>
          <div class="summary-meta">log entries</div>
        </div>
        <div class="summary-card danger" v-if="errorCount">
          <div class="summary-kicker">Errors</div>
          <div class="summary-value">{{ errorCount }}</div>
          <div class="summary-meta">error or exception logs</div>
        </div>
        <div class="summary-card" v-else>
          <div class="summary-kicker">Execution</div>
          <div class="summary-value">OK</div>
          <div class="summary-meta">no recent errors</div>
        </div>
        <div class="summary-card">
          <div class="summary-kicker">Watch Items</div>
          <div class="summary-value">{{ watchItems.length }}</div>
          <div class="summary-meta">node outputs to inspect</div>
        </div>
        <div class="summary-card" :class="{ danger: nodeEventErrorCount > 0 }">
          <div class="summary-kicker">Node Events</div>
          <div class="summary-value">{{ activeNodeEvents.length }}</div>
          <div class="summary-meta">{{ activeRunId ? 'Run ' + activeRunId : 'recent timeline events' }}</div>
        </div>
      </div>

      <NTabs type="line" animated size="small" class="tool-tabs">
        <NTabPane name="modules" tab="Code Modules">
          <div class="panel-grid">
            <div class="left-list">
              <div class="list-title">Module Index</div>
              <div v-for="moduleId in modulePaths" :key="moduleId" class="module-item" @click="emit('load', moduleId)">
                <div class="module-name">{{ moduleId }}</div>
                <div class="module-desc">{{ modulesData[moduleId]?.exports?.length || 0 }} exported functions</div>
              </div>
            </div>

            <div class="main-pane">
              <template v-if="modulesData[selectedModule]">
                <div class="pane-head">
                  <div>
                    <div class="pane-title">{{ selectedModule }}</div>
                    <div class="pane-subtitle">Edit generated Python module source for this node</div>
                  </div>
                  <NSpace :size="8">
                    <NButton size="small" type="primary" @click="emit('saveModule', { id: selectedModule, source: moduleSource })">Save Module</NButton>
                    <NButton size="small" tertiary @click="emit('load', selectedModule)">Reload</NButton>
                  </NSpace>
                </div>

                <div class="exported-list">
                  <NTag v-for="fn in modulesData[selectedModule].exports" :key="fn" size="small" round @click="emit('scroll', fn)">
                    {{ fn }}
                  </NTag>
                </div>

                <NAlert type="info" :show-icon="false" class="module-tip">
                  If a dependency import fails, check package setup and runtime logs first.
                </NAlert>

                <NInput v-model:value="moduleSource" type="textarea" :autosize="{ minRows: 12, maxRows: 18 }" />
              </template>

              <NEmpty v-else description="Select a module to inspect and edit" />
            </div>
          </div>
        </NTabPane>

        <NTabPane name="logs" tab="Logs">
          <NAlert v-if="latestErrorLog" type="error" class="log-alert">
            <template #header>Latest Error</template>
            <div class="log-alert-content">{{ latestErrorLog.text }}</div>
          </NAlert>

          <NAlert v-else type="success" class="log-alert" :show-icon="false">
            No obvious runtime errors in recent logs.
          </NAlert>

          <div class="log-list">
            <div v-for="item in logRows" :key="item.id" class="log-item" :class="item.level">
              <div class="log-pill">{{ item.level }}</div>
              <div class="log-content">{{ item.text }}</div>
            </div>
          </div>
        </NTabPane>

        <NTabPane name="watch" tab="Watch">
          <NEmpty v-if="!watchItems.length" description="No node outputs yet" />
          <div v-else class="watch-list">
            <div v-for="item in watchItems" :key="item.id" class="watch-card" :class="item.status || 'idle'">
              <div class="watch-head">
                <span class="watch-title">{{ item.label }}</span>
                <NTag size="small" :type="item.status === 'error' ? 'error' : item.status === 'done' ? 'success' : item.status === 'running' ? 'info' : 'default'">
                  {{ item.status || 'idle' }}
                </NTag>
              </div>
              <pre class="watch-value">{{ formatWatchValue(item.value) }}</pre>
            </div>
          </div>
        </NTabPane>

        <NTabPane name="trace" tab="Node Trace">
          <NEmpty v-if="!activeNodeEvents.length" description="No node events yet" />
          <div v-else class="trace-list">
            <div v-for="item in activeNodeEvents" :key="item.id" class="trace-card" :class="item.status">
              <div class="trace-head">
                <NTag size="small" :type="item.status === 'error' ? 'error' : item.status === 'ok' ? 'success' : item.status === 'running' ? 'info' : 'default'">{{ item.status }}</NTag>
                <span class="trace-phase">{{ item.phase }}</span>
                <span class="trace-time">{{ formatEventTime(item.ts) }}</span>
              </div>
              <div class="trace-node">{{ item.node_label }} ({{ item.mode }})</div>
              <div class="trace-detail">{{ item.detail || '-' }}</div>
            </div>
          </div>
        </NTabPane>

        <NTabPane name="env" tab="Env Vars">
          <NEmpty v-if="!envVars.length" description="No env vars configured" />
          <div v-else class="env-preview-list">
            <div v-for="(item, index) in envVars" :key="`${item.key}-${index}`" class="env-preview-row">
              <div>
                <div class="env-preview-key">{{ item.key || '(empty key)' }}</div>
                <div class="env-preview-meta">{{ item.secret ? 'secret' : 'plain' }}</div>
              </div>
              <div class="env-preview-value">{{ item.secret ? '••••••••' : item.value }}</div>
            </div>
          </div>
        </NTabPane>
      </NTabs>
    </div>
  </div>
</template>

<style scoped>
.bottom-panel {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  max-height: 460px;
  transition: max-height .22s ease;
  z-index: 90000;
  overflow: hidden;
}

.bottom-panel.collapsed {
  max-height: 48px;
}

.bottom-panel-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 260px;
  margin: 0 auto;
  padding: 11px 16px;
  border-radius: 16px 16px 0 0;
  text-align: center;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.94);
  color: #0f172a;
  box-shadow: 0 -10px 30px rgba(15, 23, 42, 0.08);
}

.bottom-panel-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: rgba(248, 250, 252, 0.95);
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  backdrop-filter: blur(18px);
  padding: 14px;
  min-height: 380px;
}

.panel-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.84);
  border-radius: 16px;
  padding: 14px;
}

.summary-card.danger {
  border-color: rgba(239, 68, 68, 0.22);
  background: rgba(254, 242, 242, 0.9);
}

.summary-kicker {
  font-size: 12px;
  color: #64748b;
}

.summary-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.summary-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.tool-tabs {
  min-height: 0;
}

.panel-grid {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 12px;
}

.left-list,
.log-list,
.watch-list,
.trace-list,
.env-preview-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 300px;
  overflow: auto;
}

.list-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.module-item,
.log-item,
.watch-card,
.trace-card,
.env-preview-row {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.82);
  border-radius: 14px;
  padding: 12px;
}

.module-item {
  cursor: pointer;
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}

.module-item:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.24);
  box-shadow: 0 16px 30px rgba(37, 99, 235, 0.08);
}

.module-name,
.pane-title,
.watch-title,
.env-preview-key {
  font-weight: 700;
  color: #0f172a;
}

.module-desc,
.pane-subtitle,
.env-preview-meta,
.env-preview-value {
  font-size: 12px;
  color: #64748b;
}

.main-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pane-head,
.watch-head,
.env-preview-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.exported-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.module-tip,
.log-alert {
  border-radius: 14px;
}

.log-list {
  max-height: 280px;
}

.log-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  align-items: start;
}

.log-item.error {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.9);
}

.log-item.warning {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.92);
}

.log-item.success {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(240, 253, 244, 0.92);
}

.log-pill {
  min-width: 58px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: #334155;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  text-transform: uppercase;
}

.log-content,
.log-alert-content,
.watch-value {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.watch-card.done {
  border-color: rgba(34, 197, 94, 0.18);
}

.watch-card.error {
  border-color: rgba(239, 68, 68, 0.24);
}

.watch-card.running {
  border-color: rgba(59, 130, 246, 0.2);
}

.watch-value {
  margin: 10px 0 0;
}

.trace-list {
  max-height: 300px;
}

.trace-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-card.ok {
  border-color: rgba(34, 197, 94, 0.2);
}

.trace-card.error {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.92);
}

.trace-card.running {
  border-color: rgba(59, 130, 246, 0.24);
}

.trace-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trace-phase {
  font-weight: 700;
  color: #0f172a;
}

.trace-time {
  margin-left: auto;
  color: #64748b;
  font-size: 12px;
}

.trace-node {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}

.trace-detail {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1280px) {
  .panel-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .panel-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-color-scheme: dark) {
  .bottom-panel-handle {
    background: rgba(15, 23, 42, 0.94);
    color: #e2e8f0;
    box-shadow: 0 -10px 30px rgba(2, 6, 23, 0.32);
  }

  .bottom-panel-body {
    background: rgba(15, 23, 42, 0.9);
    border-top-color: rgba(71, 85, 105, 0.38);
  }

  .summary-card,
  .module-item,
  .log-item,
  .watch-card,
  .trace-card,
  .env-preview-row {
    background: rgba(15, 23, 42, 0.74);
    border-color: rgba(71, 85, 105, 0.32);
  }

  .summary-card.danger,
  .log-item.error,
  .trace-card.error {
    background: rgba(69, 10, 10, 0.42);
    border-color: rgba(248, 113, 113, 0.28);
  }

  .log-item.warning {
    background: rgba(120, 53, 15, 0.32);
    border-color: rgba(251, 191, 36, 0.24);
  }

  .log-item.success,
  .watch-card.done,
  .trace-card.ok {
    background: rgba(20, 83, 45, 0.28);
    border-color: rgba(74, 222, 128, 0.22);
  }

  .summary-value,
  .module-name,
  .pane-title,
  .watch-title,
  .trace-phase,
  .trace-node,
  .env-preview-key {
    color: #e2e8f0;
  }

  .summary-kicker,
  .summary-meta,
  .module-desc,
  .pane-subtitle,
  .env-preview-meta,
  .env-preview-value,
  .log-content,
  .log-alert-content,
  .watch-value,
  .trace-detail,
  .trace-time {
    color: #94a3b8;
  }

  .log-pill {
    background: rgba(148, 163, 184, 0.16);
    color: #cbd5e1;
  }
}
</style>
