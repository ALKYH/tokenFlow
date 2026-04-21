<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { getBuiltinNodeConfigText, isBuiltinNode } from '../node-runtime';

const props = defineProps<{
  selectedNode: any;
  selectedFolder?: any;
  rightCollapsed: boolean;
  nodes?: any[];
  executionMode?: 'pyodide' | 'runtime';
}>();
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
  (e: 'uploadNodeTemplate'): void
  (e: 'updateNodeNote', value: string): void
  (e: 'updateExecutionModeOverride', mode: 'inherit' | 'runtime' | 'pyodide'): void
}>();

const activeTab = ref<'props' | 'styles'>('props');
const codeMirrorInstance = ref<any>(null);
const localCodeEl = ref<HTMLElement | null>(null);
const isBuiltinConfigNode = computed(() => isBuiltinNode(props.selectedNode?.category));
const builtinConfigText = computed(() => getBuiltinNodeConfigText(props.selectedNode));
const isLlmNode = computed(() => ['llm-chat', 'agent-task'].includes(props.selectedNode?.category));
const hideRawCodeEditor = computed(
  () => props.executionMode === 'runtime' && !isBuiltinConfigNode.value && props.selectedNode?.category !== 'note'
);
const executionModeOverride = computed<'inherit' | 'runtime' | 'pyodide'>(() => {
  const mode = props.selectedNode?.meta?.execution?.mode;
  if (mode === 'runtime' || mode === 'pyodide') return mode;
  return 'inherit';
});
const executionModeOptions = [
  { label: 'Inherit Workspace', value: 'inherit' },
  { label: 'Runtime', value: 'runtime' },
  { label: 'Pyodide', value: 'pyodide' }
];

const llmConfig = computed(() => {
  const config = props.selectedNode?.meta?.config || {};
  return {
    endpoint: config.endpoint || '',
    apiKey: config.apiKey || '',
    model: config.model || '',
    method: config.method || 'POST',
    inputMode: config.inputMode || 'chat',
    systemPrompt: config.systemPrompt || '',
    temperature: String(config.temperature ?? 0.2),
    topP: String(config.topP ?? 1),
    maxTokens: String(config.maxTokens ?? 1024),
    presencePenalty: String(config.presencePenalty ?? 0),
    frequencyPenalty: String(config.frequencyPenalty ?? 0),
    timeoutMs: String(config.timeoutMs ?? 30000),
    retries: String(config.retries ?? 1),
    stop: Array.isArray(config.stop) ? config.stop.join('\n') : '',
    reasoningEffort: config.reasoningEffort || 'medium',
    responsePath: config.responsePath || '',
    headers: JSON.stringify(config.headers || {}, null, 2),
    extraBody: JSON.stringify(config.extraBody || {}, null, 2)
  };
});

async function ensureCodeMirror() {
  if ((window as any).CodeMirror) return;
  const cssHref = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.css';
  const themeHref = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/theme/dracula.min.css';
  const jsSrc = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.js';
  const pyMode = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/mode/python/python.min.js';

  for (const href of [cssHref, themeHref]) {
    if (!document.querySelector(`link[href="${href}"]`)) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      document.head.appendChild(link);
    }
  }

  for (const src of [jsSrc, pyMode]) {
    if (!document.querySelector(`script[src="${src}"]`)) {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`load failed: ${src}`));
        document.head.appendChild(script);
      });
    }
  }
}

function initLocalEditor(value = '') {
  if (!localCodeEl.value || isBuiltinConfigNode.value) return;
  ensureCodeMirror().then(() => {
    if (!codeMirrorInstance.value) {
      codeMirrorInstance.value = (window as any).CodeMirror(localCodeEl.value, {
        value,
        mode: 'python',
        theme: 'dracula',
        lineNumbers: true,
        indentUnit: 4,
        viewportMargin: Infinity
      });
      return;
    }
    codeMirrorInstance.value.setValue(value || '');
    codeMirrorInstance.value.refresh?.();
  });
}

function updateLlmField(field: string, value: string) {
  const current = props.selectedNode?.meta?.config || {};
  const next = {
    ...current,
    [field]: value
  };
  if (['temperature', 'topP', 'presencePenalty', 'frequencyPenalty'].includes(field)) next[field] = Number(value);
  if (['maxTokens', 'timeoutMs', 'retries'].includes(field)) next[field] = Number(value);
  if (field === 'stop') next.stop = value.split('\n').map(item => item.trim()).filter(Boolean);
  emit('updateNodeMetaConfig', JSON.stringify(next, null, 2));
}

function updateJsonField(field: 'headers' | 'extraBody', value: string) {
  const current = props.selectedNode?.meta?.config || {};
  try {
    const parsed = JSON.parse(value || '{}');
    emit('updateNodeMetaConfig', JSON.stringify({ ...current, [field]: parsed }, null, 2));
  } catch {
    window.$message?.warning(`Invalid JSON for ${field}`);
  }
}

watch(() => props.selectedNode, nv => nextTick(() => !isBuiltinNode(nv?.category) && initLocalEditor(nv?.code || '')));
onMounted(() => nextTick(() => !isBuiltinConfigNode.value && initLocalEditor(props.selectedNode?.code || '')));

function onSave() {
  emit('saveCode', codeMirrorInstance.value ? codeMirrorInstance.value.getValue() : '');
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

function onExecutionModeOverrideChange(value: string | null) {
  const mode = value === 'runtime' || value === 'pyodide' ? value : 'inherit';
  emit('updateExecutionModeOverride', mode);
}

function isNoteNode(node: any) {
  return node?.category === 'note';
}

function getNodeFiles(node: any) {
  return Array.isArray(node?.resources) ? node.resources : [];
}

function getNodeLabel(id: string) {
  return (props.nodes || []).find(item => item.id === id)?.label || id;
}

function isChildEnabled(folder: any, childId: string) {
  return !!(folder && folder._childEnabled && folder._childEnabled[childId]);
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
          <div class="section-title">封装分组</div>
          <div class="prop-row"><label>Id</label><div class="prop-val">{{ selectedFolder.id }}</div></div>
          <div class="prop-row"><label>名称</label><input class="prop-input" :value="selectedFolder?.label" @input="e => emit('updateFolderLabel', { id: selectedFolder.id, label: (e.target as HTMLInputElement).value })" /></div>
          <div class="prop-section">
            <div class="prop-section-title">备注</div>
            <textarea class="prop-input input-textarea" :value="selectedFolder?.comment || ''" @input="e => emit('updateFolderComment', { id: selectedFolder.id, comment: (e.target as HTMLTextAreaElement).value })"></textarea>
          </div>
          <div class="prop-section">
            <div class="prop-section-title">内部节点</div>
            <div v-for="cid in selectedFolder.children || []" :key="cid" class="prop-item child-row">
              <div class="child-name">{{ getNodeLabel(cid) }}</div>
              <label class="child-toggle">
                <input type="checkbox" :checked="isChildEnabled(selectedFolder, cid)" @change="e => emit('toggleFolderChild', { folderId: selectedFolder.id, childId: cid, enabled: (e.target as HTMLInputElement).checked })" />
                启用
              </label>
            </div>
          </div>
        </div>

        <div v-else-if="selectedNode" class="section-card">
          <div class="section-title">节点信息</div>
          <div class="prop-row"><label>Id</label><div class="prop-val">{{ selectedNode.id }}</div></div>
          <div class="prop-row"><label>标题</label><input class="prop-input" :value="selectedNode?.label" @input="$emit('updateLabel', $event)" /></div>

          <div v-if="!isBuiltinConfigNode && !isNoteNode(selectedNode)" class="prop-row">
            <label>Exec Mode</label>
            <NSelect :value="executionModeOverride" :options="executionModeOptions" @update:value="onExecutionModeOverrideChange" />
          </div>

          <div class="toggle-grid">
            <label class="flag-card"><span>起始点</span><input type="checkbox" :checked="selectedNode?.isInit" @change="e => emit('updateIsInit', (e.target as HTMLInputElement).checked)" /></label>
            <label class="flag-card"><span>输出点</span><input type="checkbox" :checked="selectedNode?.isOutput" @change="e => emit('updateIsOutput', (e.target as HTMLInputElement).checked)" /></label>
          </div>

          <div class="action-row">
            <NButton size="small" tertiary @click="$emit('saveNodeTemplate')">保存到本地节点</NButton>
            <NButton size="small" type="primary" secondary @click="$emit('uploadNodeTemplate')">上传到个人节点库</NButton>
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

          <div class="prop-section" v-if="isLlmNode">
            <div class="prop-section-title">LLM 运行控制</div>
            <div class="form-grid">
              <NInput :value="llmConfig.endpoint" placeholder="Endpoint" @update:value="value => updateLlmField('endpoint', value)" />
              <NInput :value="llmConfig.model" placeholder="Model" @update:value="value => updateLlmField('model', value)" />
              <NInput :value="llmConfig.apiKey" type="password" placeholder="API Key" show-password-on="click" @update:value="value => updateLlmField('apiKey', value)" />
              <NSelect :value="llmConfig.inputMode" :options="[{ label: 'chat', value: 'chat' }, { label: 'responses', value: 'responses' }]" @update:value="value => updateLlmField('inputMode', String(value))" />
              <NInput :value="llmConfig.temperature" placeholder="temperature" @update:value="value => updateLlmField('temperature', value)" />
              <NInput :value="llmConfig.topP" placeholder="top_p" @update:value="value => updateLlmField('topP', value)" />
              <NInput :value="llmConfig.maxTokens" placeholder="max_tokens" @update:value="value => updateLlmField('maxTokens', value)" />
              <NInput :value="llmConfig.timeoutMs" placeholder="timeout_ms" @update:value="value => updateLlmField('timeoutMs', value)" />
              <NInput :value="llmConfig.retries" placeholder="retries" @update:value="value => updateLlmField('retries', value)" />
              <NSelect
                :value="llmConfig.reasoningEffort"
                :options="[{ label: 'low', value: 'low' }, { label: 'medium', value: 'medium' }, { label: 'high', value: 'high' }]"
                @update:value="value => updateLlmField('reasoningEffort', String(value))"
              />
            </div>
            <NInput type="textarea" :value="llmConfig.systemPrompt" placeholder="system prompt" :autosize="{ minRows: 3, maxRows: 6 }" @update:value="value => updateLlmField('systemPrompt', value)" />
            <NInput type="textarea" :value="llmConfig.stop" placeholder="stop tokens, one per line" :autosize="{ minRows: 2, maxRows: 4 }" @update:value="value => updateLlmField('stop', value)" />
            <NInput :value="llmConfig.responsePath" placeholder="response path, e.g. choices.0.message.content" @update:value="value => updateLlmField('responsePath', value)" />
            <NInput type="textarea" :value="llmConfig.headers" placeholder="headers JSON" :autosize="{ minRows: 3, maxRows: 6 }" @update:value="value => updateJsonField('headers', value)" />
            <NInput type="textarea" :value="llmConfig.extraBody" placeholder="extra body JSON" :autosize="{ minRows: 3, maxRows: 6 }" @update:value="value => updateJsonField('extraBody', value)" />
          </div>

          <div class="prop-section">
            <template v-if="isNoteNode(selectedNode)">
              <div class="prop-section-title">便签内容</div>
              <textarea class="prop-input input-textarea" :value="selectedNode?.meta?.note || ''" @input="onNoteInput"></textarea>
            </template>

            <template v-else-if="isBuiltinConfigNode">
              <div class="prop-section-title">节点配置</div>
              <textarea class="prop-input input-textarea code-textarea" :value="builtinConfigText" @input="onBuiltinConfigInput"></textarea>
              <div v-if="selectedNode?.category === 'pdf-parse' || selectedNode?.category === 'file-read'" class="prop-section upload-block">
                <div class="prop-section-title">文件</div>
                <input type="file" multiple @change="onBuiltinFilesChange" />
                <div v-if="getNodeFiles(selectedNode).length" class="file-list">
                  <div v-for="item in getNodeFiles(selectedNode)" :key="item.id" class="file-item">{{ item.name }}</div>
                </div>
                <NButton size="small" tertiary @click="$emit('clearNodeFiles')">清空文件</NButton>
              </div>
              <div class="action-row">
                <NButton size="small" type="primary" @click="$emit('runNode')">运行节点</NButton>
              </div>
            </template>

            <template v-else>
              <div class="prop-section-title">代码模块</div>
              <div v-if="hideRawCodeEditor" class="runtime-config-hint">
                Runtime mode composes executable code from node parameters and definition version on the backend.
              </div>
              <div v-else ref="localCodeEl" class="prop-input code-editor"></div>
              <div class="action-row">
                <NButton v-if="!hideRawCodeEditor" size="small" secondary @click="$emit('insertTemplate')">生成模板</NButton>
                <NButton size="small" type="primary" @click="$emit('runNode')">运行节点</NButton>
                <NButton v-if="!hideRawCodeEditor" size="small" @click="onSave">保存代码</NButton>
              </div>
            </template>
          </div>
        </div>

        <div v-else class="no-selection">当前没有选中的节点或分组</div>
      </div>

      <div v-if="activeTab === 'styles'">
        <div v-if="selectedNode" class="section-card">
          <div class="section-title">节点样式</div>
          <div class="prop-row">
            <label>节点颜色</label>
            <input type="color" class="color-input" :value="selectedNode?.color || '#ffffff'" @input="e => emit('updateNodeColor', (e.target as HTMLInputElement).value)" />
          </div>
          <div class="prop-section">
            <div class="prop-section-title">输入端口颜色</div>
            <div v-for="(it, i) in selectedNode.inputs || []" :key="`style-in-${i}`" class="prop-item io-color-row">
              <div class="io-label">输入 {{ Number(i) + 1 }} · {{ it }}</div>
              <input type="color" class="color-input" :value="selectedNode?.inputColors?.[i] || '#ffffff'" @input="e => emit('updateIOColor', { side: 'in', idx: Number(i), color: (e.target as HTMLInputElement).value })" />
            </div>
          </div>
          <div class="prop-section">
            <div class="prop-section-title">输出端口颜色</div>
            <div v-for="(it, i) in selectedNode.outputs || []" :key="`style-out-${i}`" class="prop-item io-color-row">
              <div class="io-label">输出 {{ Number(i) + 1 }} · {{ it }}</div>
              <input type="color" class="color-input" :value="selectedNode?.outputColors?.[i] || '#ffffff'" @input="e => emit('updateIOColor', { side: 'out', idx: Number(i), color: (e.target as HTMLInputElement).value })" />
            </div>
          </div>
        </div>
        <div v-else class="no-selection">当前没有选中的节点</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar { overflow: visible; width: 360px; background: linear-gradient(180deg, rgba(255,255,255,.95), rgba(248,250,252,.9)); border: 1px solid rgba(148,163,184,.14); border-radius: 20px; padding: 14px; box-shadow: 0 24px 60px rgba(15,23,42,.12); backdrop-filter: blur(18px); position: absolute; top: 80px; bottom: 8px; }
.sidebar.right { right: 8px; }
.sidebar-toggle { cursor: pointer; width: 38px; height: 38px; border-radius: 12px; border: 1px solid rgba(148,163,184,.16); background: rgba(255,255,255,.9); color: #334155; position: absolute; top: 26px; left: -18px; box-shadow: 0 12px 30px rgba(15,23,42,.12); }
.sidebar-content { overflow: auto; padding-right: 4px; height: 100%; }
.sidebar-kicker { font-size: 12px; color: #64748b; }
.sidebar-title { font-size: 18px; font-weight: 700; color: #0f172a; }
.sidebar-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
.sidebar-tabs button { padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(148,163,184,.14); background: rgba(255,255,255,.74); color: #475569; cursor: pointer; }
.sidebar-tabs button.active { background: rgba(37,99,235,.1); border-color: rgba(37,99,235,.2); color: #1d4ed8; }
.section-card { border: 1px solid rgba(148,163,184,.16); background: rgba(255,255,255,.78); border-radius: 16px; padding: 14px; }
.section-title, .prop-section-title { font-weight: 700; color: #0f172a; }
.prop-section { margin-top: 12px; display: grid; gap: 10px; }
.prop-row, .prop-item, .child-row, .action-row, .io-color-row { display: flex; align-items: center; gap: 8px; }
.prop-row label { width: 60px; color: #64748b; font-size: 12px; }
.prop-val { flex: 1; color: #334155; padding: 9px 12px; border-radius: 12px; background: rgba(148,163,184,.08); word-break: break-all; }
.prop-input { width: 100%; padding: 10px 12px; border-radius: 14px; border: 1px solid rgba(148,163,184,.2); background: rgba(255,255,255,.82); color: #0f172a; }
.input-textarea { min-height: 140px; resize: vertical; }
.code-textarea { font-family: Consolas, Monaco, monospace; }
.code-editor { height: 220px; background: linear-gradient(180deg, rgba(8,10,12,.96), rgba(6,7,9,.96)); border-radius: 12px; overflow: hidden; }
.runtime-config-hint { padding: 10px 12px; border-radius: 12px; border: 1px dashed rgba(59, 130, 246, .3); background: rgba(59, 130, 246, .08); color: #1e3a8a; line-height: 1.5; font-size: 12px; }
.toggle-grid, .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.flag-card { display: flex; align-items: center; justify-content: space-between; border: 1px solid rgba(148,163,184,.16); background: rgba(248,250,252,.86); border-radius: 16px; padding: 10px 12px; color: #334155; }
.prop-type { width: 110px; }
.btn-sm, .btn-mini { border: 1px solid rgba(148,163,184,.16); background: rgba(255,255,255,.84); color: #334155; cursor: pointer; }
.btn-sm { padding: 8px 10px; border-radius: 12px; }
.btn-mini { padding: 8px 10px; border-radius: 12px; }
.action-row { margin-top: 12px; flex-wrap: wrap; }
.file-list { display: flex; flex-direction: column; gap: 6px; margin: 10px 0; }
.file-item, .child-name, .io-label { color: #334155; font-size: 12px; }
.child-name, .io-label { flex: 1; }
.child-toggle { display: flex; align-items: center; gap: 6px; color: #64748b; font-size: 12px; }
.color-input { width: 48px; height: 34px; padding: 2px; border-radius: 10px; border: 1px solid rgba(148,163,184,.16); background: #fff; }
.no-selection { color: #64748b; padding: 18px 14px; border-radius: 16px; background: rgba(255,255,255,.72); border: 1px dashed rgba(148,163,184,.18); }

@media (prefers-color-scheme: dark) {
  .sidebar, .sidebar-toggle, .sidebar-tabs button, .section-card, .prop-input, .btn-sm, .btn-mini, .flag-card, .no-selection {
    background: rgba(15,23,42,.72);
    border-color: rgba(71,85,105,.3);
    color: #e2e8f0;
  }
  .sidebar-title, .section-title, .prop-section-title { color: #e2e8f0; }
  .sidebar-kicker, .prop-row label, .child-toggle, .no-selection { color: #94a3b8; }
  .prop-val { background: rgba(30,41,59,.84); color: #cbd5e1; }
  .file-item, .child-name, .io-label, .flag-card { color: #cbd5e1; }
  .sidebar-tabs button.active { background: rgba(59,130,246,.18); border-color: rgba(59,130,246,.24); color: #bfdbfe; }
  .runtime-config-hint { border-color: rgba(96, 165, 250, .45); background: rgba(30, 64, 175, .18); color: #bfdbfe; }
}
</style>
