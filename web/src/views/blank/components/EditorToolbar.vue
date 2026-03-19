<script setup lang="ts">
import { computed } from 'vue';
import SvgIcon from '@/components/custom/svg-icon.vue';

const props = defineProps<{ panMode: boolean; leftOffset?: number; rightOffset?: number; execStatus?: any; projectName?: string }>();
const emit = defineEmits<{
  (e: 'add'): void
  (e: 'runGraph'): void
  (e: 'clear'): void
  (e: 'export'): void
  (e: 'exportPy'): void
  (e: 'importPy'): void
  (e: 'importNode'): void
  (e: 'togglePan'): void
}>();

const toolbarStyle = computed(() => {
  const left = props.leftOffset ?? 12;
  const right = props.rightOffset ?? 12;
  return {
    position: 'absolute',
    top: '12px',
    left: `${left}px`,
    width: `calc(100% - ${left + right}px)`,
    zIndex: 3200
  } as any;
});

const primaryActions = [
  { key: 'add', label: 'Add Node', hint: 'A', icon: 'solar:add-circle-linear', action: () => emit('add') },
  { key: 'run', label: 'Run Graph', hint: 'Ctrl+Enter', icon: 'solar:play-circle-linear', action: () => emit('runGraph') },
  { key: 'import-node', label: 'Import Node', hint: 'Shift+I', icon: 'solar:import-linear', action: () => emit('importNode') }
];

const secondaryActions = computed(() => [
  { key: 'import-py', label: 'Import Python', hint: '.py', icon: 'solar:code-square-linear', action: () => emit('importPy') },
  { key: 'export-json', label: 'Export JSON', hint: 'Ctrl+S', icon: 'solar:export-linear', action: () => emit('export') },
  { key: 'export-py', label: 'Export Python', hint: '.py', icon: 'solar:plain-2-linear', action: () => emit('exportPy') },
  { key: 'clear', label: 'Clear Canvas', hint: 'Shift+Del', icon: 'solar:trash-bin-trash-linear', action: () => emit('clear') },
  {
    key: 'pan',
    label: props.panMode ? 'Pan Enabled' : 'Pan Mode',
    hint: 'Space',
    icon: 'solar:hand-stars-linear',
    type: props.panMode ? 'info' : 'default',
    action: () => emit('togglePan')
  }
]);
</script>

<template>
  <div class="toolbar-shell" :style="toolbarStyle">
    <div class="toolbar-brand">
      <div class="brand-mark">
        <div class="brand-dot"></div>
      </div>
      <div>
        <div class="brand-title">{{ projectName || 'Flow Studio' }}</div>
        <div class="brand-subtitle">Visual workspace for nodes, knowledge and runtime tools</div>
      </div>
    </div>

    <div class="toolbar-main">
      <div class="action-row">
        <NButton
          v-for="item in primaryActions"
          :key="item.key"
          strong
          secondary
          type="primary"
          class="toolbar-action"
          @click="item.action"
        >
          <template #icon>
            <SvgIcon :icon="item.icon" />
          </template>
          <span class="action-copy">
            <span class="action-label">{{ item.label }}</span>
            <span class="action-hint">{{ item.hint }}</span>
          </span>
        </NButton>
      </div>

      <div class="action-row">
        <NButton
          v-for="item in secondaryActions"
          :key="item.key"
          :type="item.type as any"
          tertiary
          class="toolbar-action"
          @click="item.action"
        >
          <template #icon>
            <SvgIcon :icon="item.icon" />
          </template>
          <span class="action-copy">
            <span class="action-label">{{ item.label }}</span>
            <span class="action-hint">{{ item.hint }}</span>
          </span>
        </NButton>
      </div>
    </div>

    <div class="toolbar-status">
      <NTag class="status-tag" type="default" round>Total {{ execStatus?.total || 0 }}</NTag>
      <NTag v-if="execStatus?.running" class="status-tag" type="info" round>Running {{ execStatus.running }}</NTag>
      <NTag v-if="execStatus?.done" class="status-tag" type="success" round>Done {{ execStatus.done }}</NTag>
      <NTag v-if="execStatus?.error" class="status-tag" type="error" round>Error {{ execStatus.error }}</NTag>
      <NTag v-if="execStatus?.disabled" class="status-tag" type="warning" round>Disabled {{ execStatus.disabled }}</NTag>
      <div class="status-note">Autosave enabled</div>
    </div>
  </div>
</template>

<style scoped>
.toolbar-shell {
  display: grid;
  grid-template-columns: minmax(220px, 280px) 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 10px 14px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.84));
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(18px);
}

.toolbar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(16, 185, 129, 0.14));
}

.brand-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  background: linear-gradient(135deg, #2563eb, #0f766e);
  box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.08);
}

.brand-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.brand-subtitle {
  margin-top: 2px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

.toolbar-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.toolbar-action {
  min-width: 0;
  border-radius: 12px;
}

.toolbar-action:deep(.n-button__content) {
  align-items: center;
}

.action-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.1;
}

.action-label {
  font-size: 12px;
  font-weight: 600;
}

.action-hint {
  margin-top: 2px;
  font-size: 10px;
  color: #64748b;
}

.toolbar-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.status-tag {
  backdrop-filter: blur(10px);
}

.status-note {
  font-size: 11px;
  color: #64748b;
}

@media (max-width: 1360px) {
  .toolbar-shell {
    grid-template-columns: 1fr;
  }

  .toolbar-status {
    justify-content: flex-start;
  }
}

@media (prefers-color-scheme: dark) {
  .toolbar-shell {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.88), rgba(15, 23, 42, 0.72));
    border-color: rgba(71, 85, 105, 0.42);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.36);
  }

  .brand-mark {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.16), rgba(20, 184, 166, 0.16));
  }

  .brand-title {
    color: #e2e8f0;
  }

  .brand-subtitle,
  .action-hint,
  .status-note {
    color: #94a3b8;
  }
}
</style>
