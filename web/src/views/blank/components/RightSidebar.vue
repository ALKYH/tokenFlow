<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { getBuiltinNodeConfigText, isBuiltinNode } from '../node-runtime';

const props = defineProps<{ selectedNode: any; selectedFolder?: any; rightCollapsed: boolean; nodes?: any[] }>();
const emit = defineEmits<{
  (e: 'updateLabel', payload: any): void
  (e: 'updateIO', payload: any): void
  (e: 'updateInputType', payload: any): void
  (e: 'updateOutputType', payload: any): void
  (e: 'removeIO', payload: any): void
  (e: 'addIO', payload: any): void
  (e: 'insertTemplate'): void
  (e: 'runNode'): void
  (e: 'saveCode', code: string): void
  (e: 'toggle'): void
  (e: 'updateNodeColor', color: string): void
  (e: 'updateIOColor', payload: { side: 'in' | 'out'; idx: number; color: string }): void
  (e: 'updateIsInit', isInit: boolean): void
  (e: 'updateIsOutput', isOutput: boolean): void
  (e: 'updateFolderLabel', payload: { id: string; label: string }): void
  (e: 'updateFolderComment', payload: { id: string; comment: string }): void
  (e: 'toggleFolderChild', payload: { folderId: string; childId: string; enabled: boolean }): void
  (e: 'updateNodeMetaConfig', configText: string): void
  (e: 'attachNodeFiles', payload: { files: File[] }): void
  (e: 'clearNodeFiles'): void
  (e: 'saveNodeTemplate'): void
  (e: 'updateNodeNote', value: string): void
}>();

const activeTab = ref<'props' | 'styles'>('props');
const codeMirrorInstance = ref<any>(null);
const localCodeEl = ref<HTMLElement | null>(null);
const isBuiltinConfigNode = computed(() => isBuiltinNode(props.selectedNode?.category));
const builtinConfigText = computed(() => getBuiltinNodeConfigText(props.selectedNode));

async function ensureCodeMirror() {
  if ((window as any).CodeMirror) return;
  const cssHref = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.css';
  const themeHref = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/theme/dracula.min.css';
  const jsSrc = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.js';
  const pyMode = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/mode/python/python.min.js';

  if (!document.querySelector(`link[href="${cssHref}"]`)) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssHref;
    document.head.appendChild(link);
  }
  if (!document.querySelector(`link[href="${themeHref}"]`)) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = themeHref;
    document.head.appendChild(link);
  }
  if (!document.querySelector(`script[src="${jsSrc}"]`)) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = jsSrc;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('codemirror load failed'));
      document.head.appendChild(script);
    });
  }
  if (!document.querySelector(`script[src="${pyMode}"]`)) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = pyMode;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('codemirror python mode load failed'));
      document.head.appendChild(script);
    });
  }
}

function initLocalEditor(value = '') {
  if (!localCodeEl.value || isBuiltinConfigNode.value) return;

  ensureCodeMirror()
    .then(() => {
      if (!(window as any).CodeMirror) return;

      try {
        const prevEls = localCodeEl.value?.querySelectorAll('.CodeMirror') || [];
        prevEls.forEach((node: Element) => node.remove());
      } catch {}

      try {
        if (codeMirrorInstance.value && codeMirrorInstance.value.getWrapperElement) {
          const wrapper = codeMirrorInstance.value.getWrapperElement();
          if (wrapper && (!localCodeEl.value || !localCodeEl.value.contains(wrapper))) {
            const prev = codeMirrorInstance.value.getValue && codeMirrorInstance.value.getValue();
            if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
            codeMirrorInstance.value = null;
            value = value || prev || '';
          }
        }
      } catch {}

      if (!codeMirrorInstance.value) {
        codeMirrorInstance.value = (window as any).CodeMirror(localCodeEl.value, {
          value: value || '',
          mode: 'python',
          theme: 'dracula',
          lineNumbers: true,
          indentUnit: 4,
          readOnly: false,
          viewportMargin: Infinity
        });
      } else {
        codeMirrorInstance.value.setValue(value || '');
        codeMirrorInstance.value.refresh?.();
      }
    })
    .catch(err => console.warn('CodeMirror load error', err));
}

watch(
  () => props.selectedNode,
  nv => {
    nextTick(() => {
      if (!isBuiltinNode(nv?.category)) {
        initLocalEditor(nv?.code || '');
      }
    });
  }
);

onMounted(() => {
  nextTick(() => {
    if (!isBuiltinConfigNode.value) {
      initLocalEditor(props.selectedNode?.code || '');
    }
  });
});

function onSave() {
  const code = codeMirrorInstance.value ? codeMirrorInstance.value.getValue() : '';
  emit('saveCode', code);
}

function onNodeColorInput(e: Event) {
  emit('updateNodeColor', (e.target as HTMLInputElement).value);
}

function onIOColorInput(side: 'in' | 'out', idx: number, e: Event) {
  emit('updateIOColor', { side, idx, color: (e.target as HTMLInputElement).value });
}

function onBuiltinConfigInput(e: Event) {
  emit('updateNodeMetaConfig', (e.target as HTMLTextAreaElement).value);
}

function onBuiltinFilesChange(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files || []);
  emit('attachNodeFiles', { files });
  (e.target as HTMLInputElement).value = '';
}

function onNoteInput(e: Event) {
  emit('updateNodeNote', (e.target as HTMLTextAreaElement).value);
}

function isNoteNode(node: any) {
  return node?.category === 'note';
}

function getNodeFiles(node: any) {
  return Array.isArray(node?.resources) ? node.resources : [];
}

function getNodeLabel(id: string) {
  try {
    const node = (props.nodes || []).find(item => item.id === id);
    return node ? node.label || id : id;
  } catch {
    return id;
  }
}

function isChildEnabled(folder: any, childId: string) {
  try {
    return !!(folder && folder._childEnabled && folder._childEnabled[childId]);
  } catch {
    return true;
  }
}

function handleToggleChild(folderId: string, childId: string, e: Event) {
  emit('toggleFolderChild', {
    folderId,
    childId,
    enabled: (e.target as HTMLInputElement).checked
  });
}

function onIsInitChange(e: Event) {
  emit('updateIsInit', (e.target as HTMLInputElement).checked);
}

function onIsOutputChange(e: Event) {
  emit('updateIsOutput', (e.target as HTMLInputElement).checked);
}

function onFolderLabelInput(e: Event) {
  if (!props.selectedFolder) return;
  emit('updateFolderLabel', { id: props.selectedFolder.id, label: (e.target as HTMLInputElement).value });
}

function onFolderCommentInput(e: Event) {
  if (!props.selectedFolder) return;
  emit('updateFolderComment', { id: props.selectedFolder.id, comment: (e.target as HTMLTextAreaElement).value });
}
</script>

<template>
  <aside class="sidebar right" :class="{ collapsed: rightCollapsed }" aria-hidden="false">
    <button class="sidebar-toggle" :title="rightCollapsed ? '展开属性面板' : '收起属性面板'" @click="$emit('toggle')">
      {{ rightCollapsed ? '<' : '>' }}
    </button>

    <div v-show="!rightCollapsed" class="sidebar-content">
      <div class="sidebar-head">
        <div>
          <div class="sidebar-kicker">Inspector</div>
          <div class="sidebar-title">属性与样式</div>
        </div>
      </div>

      <div class="sidebar-tabs">
        <button :class="{ active: activeTab === 'props' }" @click="activeTab = 'props'">属性</button>
        <button :class="{ active: activeTab === 'styles' }" @click="activeTab = 'styles'">样式</button>
      </div>

      <div v-if="activeTab === 'props'">
        <div v-if="selectedFolder" class="section-card">
          <div class="section-title">封装文件夹</div>
          <div class="prop-row"><label>Id</label><div class="prop-val">{{ selectedFolder.id }}</div></div>
          <div class="prop-row"><label>名称</label><input class="prop-input" :value="selectedFolder?.label" @input="onFolderLabelInput" /></div>
          <div class="prop-section">
            <div class="prop-section-title">备注</div>
            <textarea class="prop-input input-textarea" :value="selectedFolder?.comment || ''" @input="onFolderCommentInput"></textarea>
          </div>
          <div class="prop-section">
            <div class="prop-section-title">内部节点</div>
            <div v-for="cid in selectedFolder.children || []" :key="cid" class="prop-item child-row">
              <div class="child-name">{{ getNodeLabel(cid) }}</div>
              <label class="child-toggle">
                <input type="checkbox" :checked="isChildEnabled(selectedFolder, cid)" @change="e => handleToggleChild(selectedFolder.id, cid, e)" />
                启用
              </label>
            </div>
          </div>
        </div>

        <div v-else-if="selectedNode" class="section-card">
          <div class="section-title">节点信息</div>
          <div class="prop-row"><label>Id</label><div class="prop-val">{{ selectedNode.id }}</div></div>
          <div class="prop-row"><label>标题</label><input class="prop-input" :value="selectedNode?.label" @input="$emit('updateLabel', $event)" /></div>

          <div class="toggle-grid">
            <label class="flag-card">
              <span>起始点</span>
              <input type="checkbox" :checked="selectedNode?.isInit" @change="onIsInitChange" />
            </label>
            <label class="flag-card">
              <span>输出点</span>
              <input type="checkbox" :checked="selectedNode?.isOutput" @change="onIsOutputChange" />
            </label>
          </div>

          <div class="prop-section">
            <div class="prop-section-title">输入端口</div>
            <div v-for="(it, i) in selectedNode.inputs || []" :key="`in-${i}`" class="prop-item io-row">
              <input class="prop-input" :value="it" @input="$emit('updateIO', { side: 'in', idx: i, event: $event })" />
              <input class="prop-input prop-type" :value="selectedNode?.inputTypes?.[i] || ''" placeholder="type" @input="$emit('updateInputType', { idx: i, event: $event })" />
              <button class="btn-mini" @click="$emit('removeIO', { side: 'in', idx: i })">-</button>
            </div>
            <button class="btn-sm" @click="$emit('addIO', 'in')">添加输入</button>
          </div>

          <div class="prop-section">
            <div class="prop-section-title">输出端口</div>
            <div v-for="(it, i) in selectedNode.outputs || []" :key="`out-${i}`" class="prop-item io-row">
              <input class="prop-input" :value="it" @input="$emit('updateIO', { side: 'out', idx: i, event: $event })" />
              <input class="prop-input prop-type" :value="selectedNode?.outputTypes?.[i] || ''" placeholder="type" @input="$emit('updateOutputType', { idx: i, event: $event })" />
              <button class="btn-mini" @click="$emit('removeIO', { side: 'out', idx: i })">-</button>
            </div>
            <button class="btn-sm" @click="$emit('addIO', 'out')">添加输出</button>
          </div>

          <div class="prop-section">
            <template v-if="isNoteNode(selectedNode)">
              <div class="prop-section-title">便签内容</div>
              <textarea class="prop-input input-textarea" :value="selectedNode?.meta?.note || ''" @input="onNoteInput"></textarea>
              <div class="action-row">
                <NButton size="small" tertiary @click="$emit('saveNodeTemplate')">保存为本地节点</NButton>
              </div>
            </template>

            <template v-else-if="isBuiltinConfigNode">
              <div class="prop-section-title">节点配置</div>
              <textarea class="prop-input input-textarea code-textarea" :value="builtinConfigText" @input="onBuiltinConfigInput"></textarea>

              <div v-if="selectedNode?.category === 'pdf-parse'" class="prop-section upload-block">
                <div class="prop-section-title">PDF 文件</div>
                <input type="file" accept=".pdf,application/pdf" multiple @change="onBuiltinFilesChange" />
                <div v-if="getNodeFiles(selectedNode).length" class="file-list">
                  <div v-for="item in getNodeFiles(selectedNode)" :key="item.id" class="file-item">{{ item.name }}</div>
                </div>
                <NButton size="small" tertiary @click="$emit('clearNodeFiles')">清空文件</NButton>
              </div>

              <div class="action-row">
                <NButton size="small" type="primary" @click="$emit('runNode')">运行节点</NButton>
                <NButton size="small" tertiary @click="$emit('saveNodeTemplate')">保存为本地节点</NButton>
                <div class="last-result">Last: {{ selectedNode?.lastResult }}</div>
              </div>
            </template>

            <template v-else>
              <div class="prop-section-title">代码模块</div>
              <div ref="localCodeEl" class="prop-input code-editor"></div>
              <div class="action-row">
                <NButton size="small" secondary @click="$emit('insertTemplate')">生成模板</NButton>
                <NButton size="small" type="primary" @click="$emit('runNode')">运行节点</NButton>
                <NButton size="small" @click="onSave">保存代码</NButton>
                <div class="last-result">Last: {{ selectedNode?.lastResult }}</div>
              </div>
            </template>
          </div>
        </div>

        <div v-else class="no-selection">当前没有选中的节点或文件夹</div>
      </div>

      <div v-if="activeTab === 'styles'">
        <div v-if="selectedNode" class="section-card">
          <div class="section-title">节点样式</div>
          <div class="prop-row">
            <label>节点颜色</label>
            <input type="color" class="color-input" :value="selectedNode?.color || '#ffffff'" @input="onNodeColorInput" />
          </div>

          <div class="prop-section">
            <div class="prop-section-title">输入端口颜色</div>
            <div v-for="(it, i) in selectedNode.inputs || []" :key="`style-in-${i}`" class="prop-item io-color-row">
              <div class="io-label">输入 {{ Number(i) + 1 }} · {{ it }}</div>
              <input type="color" class="color-input" :value="selectedNode?.inputColors?.[i] || '#ffffff'" @input="e => onIOColorInput('in', Number(i), e)" />
            </div>
          </div>

          <div class="prop-section">
            <div class="prop-section-title">输出端口颜色</div>
            <div v-for="(it, i) in selectedNode.outputs || []" :key="`style-out-${i}`" class="prop-item io-color-row">
              <div class="io-label">输出 {{ Number(i) + 1 }} · {{ it }}</div>
              <input type="color" class="color-input" :value="selectedNode?.outputColors?.[i] || '#ffffff'" @input="e => onIOColorInput('out', Number(i), e)" />
            </div>
          </div>
        </div>

        <div v-else class="no-selection">当前没有选中的节点</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  overflow: visible;
  width: 360px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.9));
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  padding: 14px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(18px);
  position: absolute;
  top: 80px;
  bottom: 8px;
}

.sidebar.right {
  right: 8px;
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
  left: -18px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.12);
}

.sidebar-content {
  overflow: auto;
  padding-right: 4px;
  height: 100%;
}

.sidebar-head {
  margin-bottom: 12px;
}

.sidebar-kicker {
  font-size: 12px;
  color: #64748b;
}

.sidebar-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.sidebar-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.sidebar-tabs button {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(255, 255, 255, 0.74);
  color: #475569;
  cursor: pointer;
}

.sidebar-tabs button.active {
  background: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.2);
  color: #1d4ed8;
}

.section-card {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.78);
  border-radius: 16px;
  padding: 14px;
}

.section-title,
.prop-section-title {
  font-weight: 700;
  color: #0f172a;
}

.prop-section {
  margin-top: 12px;
}

.prop-row,
.prop-item,
.child-row,
.action-row,
.io-color-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.prop-row {
  padding: 8px 0;
}

.prop-row label {
  width: 60px;
  color: #64748b;
  font-size: 12px;
}

.prop-val {
  flex: 1;
  color: #334155;
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.08);
  word-break: break-all;
}

.prop-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.82);
  color: #0f172a;
}

.input-textarea {
  min-height: 160px;
  resize: vertical;
}

.code-textarea {
  font-family: Consolas, Monaco, monospace;
}

.code-editor {
  height: 220px;
  background: linear-gradient(180deg, rgba(8, 10, 12, 0.96), rgba(6, 7, 9, 0.96));
  border-radius: 12px;
  overflow: hidden;
}

.toggle-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.flag-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.86);
  border-radius: 16px;
  padding: 10px 12px;
  color: #334155;
}

.io-row {
  margin-top: 8px;
}

.prop-type {
  width: 110px;
}

.btn-sm,
.btn-mini {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.84);
  color: #334155;
  cursor: pointer;
}

.btn-sm {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 12px;
}

.btn-mini {
  padding: 8px 10px;
  border-radius: 12px;
}

.action-row {
  margin-top: 12px;
  flex-wrap: wrap;
}

.last-result {
  margin-left: auto;
  font-size: 12px;
  color: #64748b;
  word-break: break-all;
}

.upload-block {
  padding-top: 6px;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 0;
}

.file-item,
.child-name,
.io-label {
  color: #334155;
  font-size: 12px;
}

.child-name,
.io-label {
  flex: 1;
}

.child-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
}

.color-input {
  width: 48px;
  height: 34px;
  padding: 2px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: #fff;
}

.no-selection {
  color: #64748b;
  padding: 18px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px dashed rgba(148, 163, 184, 0.18);
}

@media (prefers-color-scheme: dark) {
  .sidebar {
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.76));
    border-color: rgba(71, 85, 105, 0.34);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.34);
  }

  .sidebar-toggle,
  .sidebar-tabs button,
  .section-card,
  .prop-input,
  .btn-sm,
  .btn-mini,
  .flag-card,
  .no-selection {
    background: rgba(15, 23, 42, 0.72);
    border-color: rgba(71, 85, 105, 0.3);
    color: #e2e8f0;
  }

  .sidebar-title,
  .section-title,
  .prop-section-title {
    color: #e2e8f0;
  }

  .sidebar-kicker,
  .prop-row label,
  .last-result,
  .child-toggle,
  .no-selection {
    color: #94a3b8;
  }

  .prop-val {
    background: rgba(30, 41, 59, 0.84);
    color: #cbd5e1;
  }

  .file-item,
  .child-name,
  .io-label,
  .flag-card {
    color: #cbd5e1;
  }

  .sidebar-tabs button.active {
    background: rgba(59, 130, 246, 0.18);
    border-color: rgba(59, 130, 246, 0.24);
    color: #bfdbfe;
  }
}
</style>
