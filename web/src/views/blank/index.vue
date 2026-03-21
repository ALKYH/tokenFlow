<!-- eslint-disable @typescript-eslint/no-unused-vars -->

<script setup lang="ts">
    import { ref, reactive, onMounted, onBeforeUnmount, computed, watch } from 'vue';
    import { useRoute } from 'vue-router';
    import type { CSSProperties } from 'vue';
    import { edgePath, NODE_W, headerHeight, rowHeight, BODY_PADDING } from './editor-core';
    import useEditorInteractions from './useEditorInteractions';
    // import { topoSort } from './parser'; // unused
    import type { Node, Edge } from './editor-core';
    import EditorToolbar from './components/EditorToolbar.vue';
    import LeftSidebar from './components/LeftSidebar.vue';
    import RightSidebar from './components/RightSidebar.vue';
    import BottomPanel from './components/BottomPanel.vue';
    import DebugPanel from './components/DebugPanel.vue';
    import {
      createNodeFromPreset,
      getNodePreset,
      NODE_LIBRARY_SECTIONS,
      WORKFLOW_TEMPLATES,
      WORKFLOW_TEMPLATE_GROUPS
    } from './node-catalog';
    import { isBuiltinNode, runBuiltinNode } from './node-runtime';
    import { KNOWLEDGE_NODE_PRESETS, createKnowledgeNode, isKnowledgeNode } from './knowledge-pipeline';
    import {
      consumePendingWorkspaceImport,
      fetchMyPluginLibrary,
      fetchWorkspaceById,
      getStoredAccessToken,
      loadWorkspaceSnapshots,
      uploadPlugin
    } from '@/service/api';

    const areaRef = ref<HTMLElement | null>(null);
    const route = useRoute();
    const nodes = reactive<Node[]>([]);
    const folders = reactive<Array<any>>([]);
    const edges = reactive<Edge[]>([]);

    let nodeSeq = 1;

    const dragging = {
      node: null as Node | null,
      offsetX: 0,
      offsetY: 0,
      multi: false,
      offsets: {} as Record<string, { offsetX: number; offsetY: number }>
    };

    const tempEdge = ref<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
    const edgeStart = ref<{ nodeId: string; type: 'in' | 'out'; portIndex: number; x: number; y: number; pointerId?: number } | null>(null);
    const nodeHoverPreview = ref<{ visible: boolean; x: number; y: number; node: Node | null }>({ visible: false, x: 0, y: 0, node: null });
    const suggestionModalVisible = ref(false);
    const selectedIds = ref<string[]>([]);
    const leftCollapsed = ref(false);
    const rightCollapsed = ref(false);
    const LEFT_SIDEBAR_WIDTH = 320;
    const RIGHT_SIDEBAR_WIDTH = 360;
    const toolbarLeftOffset = computed(() => (leftCollapsed.value ? 24 : LEFT_SIDEBAR_WIDTH + 28));
    const toolbarRightOffset = computed(() => (rightCollapsed.value ? 24 : RIGHT_SIDEBAR_WIDTH + 28));
    const selectedNode = computed(() => nodes.find(n => n.id === (selectedIds.value[0] || null)) || null);
    const selectedFolder = computed(() => folders.find(f => f.id === (selectedIds.value[0] || null)) || null);
    const selectedNodeId = computed(() => selectedNode?.value ? selectedNode.value.id : '');

    // execution status summary (counts of nodes by status)
    const execStatus = computed(() => {
      const res = { total: nodes.length, running: 0, error: 0, done: 0, idle: 0, disabled: 0 } as Record<string, number> | any;
      for (const n of nodes) {
        const s = (n as any).status || 'idle';
        if (s === 'running') res.running++;
        else if (s === 'error') res.error++;
        else if (s === 'done') res.done++;
        else if (s === 'disabled') res.disabled++;
        else res.idle++;
      }
      return res;
    });
    const projectConfig = computed(() => ({
      name: moduleMeta.name,
      description: moduleMeta.description,
      requires: moduleMeta.requires
    }));
    const watchItems = computed(() =>
      nodes
        .filter(n => n.lastResult !== null && n.lastResult !== undefined)
        .map(n => ({
          id: n.id,
          label: n.label || n.id,
          status: (n as any).status || 'idle',
          value: n.lastResult
        }))
    );
    const workspaceSuggestions = computed(() => {
      const items: Array<{ level: 'info' | 'warning' | 'error'; title: string; detail: string }> = [];
      const initCount = nodes.filter(n => (n as any).isInit).length;
      const outputCount = nodes.filter(n => (n as any).isOutput).length;
      if (initCount === 0) items.push({ level: 'error', title: '缺少起始点', detail: '建议至少保留一个起始点节点，否则流水线缺少明确入口。' });
      if (outputCount === 0) items.push({ level: 'warning', title: '未标记输出点', detail: '输出点是可选的，但标记输出节点后更便于封装、调试和模板复用。' });
      if (nodes.length > 0 && edges.length === 0) items.push({ level: 'info', title: '节点尚未连线', detail: '当前已有节点但没有连线，可通过端口拖拽连线形成流程。' });
      if (!items.length) items.push({ level: 'info', title: '结构检查通过', detail: '当前模块包含起始点，且整体结构适合继续编辑和封装。' });
      return items;
    });

    // toolbar offset logic (no longer used when toolbar is inside editor-area)
    const SIDEBAR_W = 280;
    const GAP = 8;

    // wrappers for component-emitted payloads (avoid implicit any in template)
    function onUpdateIO(payload: { side: 'in' | 'out'; idx: number; event: Event }) {
      handleNodeIOInput(selectedNodeId.value, payload.side, payload.idx, payload.event);
    }

    function onUpdateInputType(payload: { idx: number; event: Event }) {
      handleNodeInputTypeInput(selectedNodeId.value, payload.idx, payload.event);
    }

    function onUpdateOutputType(payload: { idx: number; event: Event }) {
      handleNodeOutputTypeInput(selectedNodeId.value, payload.idx, payload.event);
    }

    function onAddIO(side: 'in' | 'out') {
      addNodeIO(selectedNodeId.value, side);
    }

    function onRemoveIO(payload: { side: 'in' | 'out'; idx: number }) {
      removeNodeIO(selectedNodeId.value, payload.side, payload.idx);
    }
    // let capturedEl: HTMLElement | null = null; // reserved for future use
    const hoverPort = ref<{ nodeId: string; type: 'in' | 'out'; index: number; invalid?: boolean } | null>(null);
    const debugLogs = reactive<string[]>([]);
    const pyodide = ref<any>(null);
    const pyReady = ref(false);
    const pyCode = ref(`print("hello from pyodide")`);
    const pyPackages = ref('');
    const moduleMeta = reactive({ name: 'TokenFlow Workspace', description: 'Visual pipeline editor for nodes and knowledge workflows', requires: '' });
    const envVars = reactive<Array<{ key: string; value: string; secret?: boolean }>>([
      { key: 'EMBEDDING_ENDPOINT', value: '', secret: false },
      { key: 'EMBEDDING_API_KEY', value: '', secret: true }
    ]);
    const savedNodeTemplates = ref<any[]>([]);
    const cloudModuleCount = ref(0);
    const nodeTemplateStorageKey = 'tokenflow.local-node-templates.v1';
    const workspaceStorageKey = 'tokenflow.workspace.modules.v1';
    let workspaceSaveTimer: ReturnType<typeof setTimeout> | null = null;
    const bottomCollapsed = ref(true);
    const modulePaths = ref<string[]>([]);
    const modulesData = reactive<Record<string, { source: string; exports: string[]; functions?: Array<{ name: string; params: string[]; hasReturn: boolean }> }>>({});
    const selectedModule = ref('');
    const codeEl = ref<HTMLElement | null>(null);
    const rowGap = 6;
    const marquee = ref({ visible: false, x: 0, y: 0, w: 0, h: 0 });
    const marqueeHits = ref<string[]>([]);
    const marqueeStart = { x: 0, y: 0, shift: false };


    // viewport (pan & zoom) state
    const viewScale = ref(1);
    const viewOffset = reactive({ x: 0, y: 0 });
    const panMode = ref(false); // when true, dragging background pans the viewport
    const isPanning = ref(false);
    const panStart = { x: 0, y: 0, offsetX: 0, offsetY: 0 };
    const viewportStyle = computed(() => ({ transform: `translate(${viewOffset.x}px, ${viewOffset.y}px) scale(${viewScale.value})`, transformOrigin: '0 0' }));

    // interaction handlers moved to composable
    const interactions = useEditorInteractions({
      areaRef,
      nodes,
      edges,
      selectedIds,
      dragging,
      viewScale,
      viewOffset,
      marquee,
      marqueeHits,
      marqueeStart,
      edgeStart,
      tempEdge,
      hoverPort,
      folders,
      panMode,
      isPanning,
      panStart,
      debugLogs
    });

    function logDebug(...args: any[]) {
      try {
        const msg = args.map(a => (typeof a === 'string' ? a : JSON.stringify(a))).join(' ');
        debugLogs.unshift(`${new Date().toISOString()} ${msg}`);
        if (debugLogs.length > 80) debugLogs.pop();
      } catch (e) {}
      try { console.debug(...args); } catch (e) {}
    }

    async function ensureHighlighter() {
      if ((window as any).hljs) return;
      // inject highlight.js CSS + JS
      const cssHref = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
      const jsSrc = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js';
      if (!document.querySelector(`link[href="${cssHref}"]`)) {
        const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = cssHref; document.head.appendChild(l);
      }
      if (!document.querySelector(`script[src="${jsSrc}"]`)) {
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement('script'); s.src = jsSrc; s.onload = () => resolve(); s.onerror = () => reject(new Error('hljs load failed')); document.head.appendChild(s);
        });
      }
      // register common languages if needed (highlight.js auto-detect is fine)
    }

    async function loadModule(path: string) {
      // now modules are derived from node code blocks
      selectedModule.value = path;
      await ensureHighlighter();
      setTimeout(() => { if (codeEl.value) (window as any).hljs.highlightElement(codeEl.value as HTMLElement); }, 50);
    }



    function scrollToExport(fnName: string) {
      const md = modulesData[selectedModule.value];
      if (!md) return;
      const idx = md.source.indexOf(fnName);
      if (idx >= 0 && codeEl.value) {
        const el = codeEl.value;
        // approximate: create a temporary anchor by highlighting the function name in the displayed text
        // simple approach: scroll to start of code element
        el.scrollTop = Math.max(0, el.textContent ? el.textContent.indexOf(fnName) : 0);
      }
    }

    function rebuildNodeModules() {
      modulePaths.value = nodes.map(n => n.id);
      for (const n of nodes) {
        const src = (n as any).code || '';
        const functions: Array<{ name: string; params: string[]; hasReturn: boolean }> = [];
        // match def name and param list
        const re = /^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:/gm;
        let m: RegExpExecArray | null;
        while ((m = re.exec(src)) !== null) {
          const name = m[1];
          const paramsRaw = m[2] || '';
          const params = paramsRaw.split(',').map(s => s.trim()).filter(s => !!s).map(p => p.replace(/=.*/,'').trim());
          // simple heuristic: look for 'return' keyword after this function definition until next def or end
          const from = m.index + m[0].length;
          const rest = src.slice(from);
          const nextDef = rest.search(/^\s*def\s+/m);
          const body = nextDef >= 0 ? rest.slice(0, nextDef) : rest;
          const hasReturn = /\breturn\b/.test(body);
          functions.push({ name, params, hasReturn });
        }
        const exports = functions.map(f => f.name);
        modulesData[n.id] = { source: src || '# (no code)', exports, functions };
      }
      // if selectedModule no longer exists, clear
      if (selectedModule.value && !modulePaths.value.includes(selectedModule.value)) selectedModule.value = '';
    }

    // expose pushDebug to Python via js.pushDebug
    (window as any).pushDebug = (msg: any) => {
      try {
        debugLogs.unshift(`${new Date().toISOString()} ${String(msg)}`);
        if (debugLogs.length > 120) debugLogs.pop();
      } catch (e) {}
    };

    // expose a helper for Python to write back node results as JSON string
    (window as any).setNodeResult = (nodeId: string, jsonStr: string) => {
      try {
        const n = nodes.find(x => x.id === nodeId as string);
        if (n) {
          try {
            // try parse JSON, fallback to raw string
            n.lastResult = JSON.parse(jsonStr);
          } catch (e) {
            n.lastResult = jsonStr;
          }
        }
        debugLogs.unshift(`${new Date().toISOString()} setNodeResult ${nodeId} ` + String(jsonStr));
        if (debugLogs.length > 120) debugLogs.pop();
      } catch (e) {
        try { console.warn('setNodeResult error', e); } catch (e) {}
      }
    };

    async function loadPyodideAndInit() {
      if (pyReady.value) return;
      const base = 'https://cdn.jsdelivr.net/pyodide/v0.23.4/full/';
      // Load loader script if missing
      if (!(window as any).loadPyodide) {
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement('script');
          s.src = base + 'pyodide.js';
          s.onload = () => resolve();
          s.onerror = () => reject(new Error('pyodide load failed'));
          document.head.appendChild(s);
        });
      }
      try {
        pyodide.value = await (window as any).loadPyodide({ indexURL: base });
        // try to wire basic stdout/stderr if supported
        try {
          if ((pyodide.value as any).setStdout) {
            (pyodide.value as any).setStdout((txt: string) => { debugLogs.unshift(`${new Date().toISOString()} stdout: ${String(txt)}`); if (debugLogs.length > 120) debugLogs.pop(); });
          }
          if ((pyodide.value as any).setStderr) {
            (pyodide.value as any).setStderr((txt: string) => { debugLogs.unshift(`${new Date().toISOString()} stderr: ${String(txt)}`); if (debugLogs.length > 120) debugLogs.pop(); });
          }
        } catch (e) {}
        pyReady.value = true;
        logDebug('pyodide ready');
      } catch (err) {
        logDebug('loadPyodide error', err?.toString ? err.toString() : err);
        throw err;
      }
    }

    async function runPy() {
      if (!pyReady.value) {
        logDebug('pyodide not ready yet');
        return;
      }
      const code = pyCode.value || '';
      // Wrap user code so that prints and errors are forwarded to js.pushDebug
      const wrapped = `\nimport sys\nfrom js import pushDebug\nclass _W:\n    def write(self,s):\n        try:\n            if s is None: return\n            s2 = str(s)\n            if s2.strip():\n                pushDebug(s2)\n        except Exception as e:\n            pass\n    def flush(self):\n        pass\nsys.stdout = _W()\nsys.stderr = _W()\n\ntry:\n${code.split('\n').map(line=> '    ' + line).join('\n')}\nexcept Exception as _e:\n    pushDebug('py exception: ' + str(_e))\n`;
      try {
        await pyodide.value.runPythonAsync(wrapped);
      } catch (err: any) {
        logDebug('py error: ' + (err?.toString ? err.toString() : String(err)));
      }
    }

    function handleDebugRun(code: string) {
      logDebug('handleDebugRun invoked', 'pyReady=' + String(pyReady.value));
      // coerce code to string if a ref or other type was passed
      const payload = (code && typeof code !== 'string') ? ((code as any).value ?? String(code)) : (code || '');
      pyCode.value = payload as string;
      runPy().catch((e) => logDebug('runPy threw', e?.toString ? e.toString() : e));
    }

    function handleDebugInstall(pkgs: string) {
      logDebug('handleDebugInstall invoked', 'pyReady=' + String(pyReady.value), pkgs);
      const payload = (pkgs && typeof pkgs !== 'string') ? ((pkgs as any).value ?? String(pkgs)) : (pkgs || '');
      pyPackages.value = payload as string;
      installPackages().catch((e) => logDebug('installPackages threw', e?.toString ? e.toString() : e));
    }

    // wrappers for template -> use .value for computed refs
    function handleSaveCode(code: string) {
      const id = selectedNodeId.value || '';
      if (!id) {
        logDebug('handleSaveCode: no node selected');
        return;
      }
      updateNodeCode(id, String(code || ''));
    }

    function handleUpdateNodeMetaConfig(configText: string) {
      const id = selectedNodeId.value || '';
      if (!id) {
        logDebug('handleUpdateNodeMetaConfig: no node selected');
        return;
      }
      updateNodeMetaConfig(id, String(configText || '{}'));
    }

    function handleAttachNodeFiles(payload: { files: File[] }) {
      const id = selectedNodeId.value || '';
      if (!id) {
        logDebug('handleAttachNodeFiles: no node selected');
        return;
      }
      attachNodeFiles(id, payload?.files || []);
    }

    function handleClearNodeFiles() {
      const id = selectedNodeId.value || '';
      if (!id) {
        logDebug('handleClearNodeFiles: no node selected');
        return;
      }
      clearNodeFiles(id);
    }

    function handleUpdateNodeNote(note: string) {
      const id = selectedNodeId.value || '';
      if (!id) return;
      updateNodeNote(id, note);
    }

    function handleRunSelectedNode() {
      const id = selectedNodeId.value || '';
      if (!id) { logDebug('handleRunSelectedNode: no node selected'); return; }
      runNode(id).catch(e => logDebug('runNode threw', e?.toString ? e.toString() : e));
    }

    function handleInsertTemplate() {
      const id = selectedNodeId.value || '';
      if (!id) { logDebug('handleInsertTemplate: no node selected'); return; }
      insertTemplate(id);
    }

    function handleUpdateIsInit(isInit: boolean) {
      const id = selectedNodeId.value || '';
      if (!id) { logDebug('handleUpdateIsInit: no node selected'); return; }
      updateNodeIsInit(id, isInit);
    }

    function handleSaveModule(payload: { id: string; source: string }) {
      try {
        const id = payload && payload.id ? payload.id : '';
        const src = payload && typeof payload.source === 'string' ? payload.source : '';
        if (!id) { logDebug('handleSaveModule: no id provided'); return; }
        // update node code and modulesData
        updateNodeCode(id, src);
        logDebug('handleSaveModule: saved module', id);
      } catch (e) {
        logDebug('handleSaveModule error', e?.toString ? e.toString() : e);
      }
    }

    async function runNode(nodeId: string) {
      const node = nodes.find(n => n.id === nodeId);
      if (!node) {
        logDebug('node not found', nodeId);
        return;
      }
      // if this node is a folded-folder representative, run its backup subgraph instead
      try {
        const folder = folders.find((f: any) => f._foldedNodeId === nodeId);
        if (folder && folder._backup) {
          logDebug('runNode: detected folded folder node, executing backup subgraph for', nodeId);
          // prepare backup data
          const backup = folder._backup;
          const bNodes: any[] = (backup.nodes || []).map((n: any) => Object.assign({}, n));
          const bEdges: any[] = (backup.edges || []).map((e: any) => Object.assign({}, e));
          const bNodeIds = new Set(bNodes.map(n => n.id));

          // input nodes inside the folder (marked isInit)
          const inputNodes = bNodes.filter(n => n.isInit);

          // compute topological order for bNodes using only internal edges
          const incomingCount: Record<string, number> = {};
          const outgoingMap: Record<string, any[]> = {};
          for (const n of bNodes) { incomingCount[n.id] = 0; outgoingMap[n.id] = []; }
          for (const e of bEdges) {
            if (!bNodeIds.has(e.from.nodeId) || !bNodeIds.has(e.to.nodeId)) continue;
            incomingCount[e.to.nodeId] = (incomingCount[e.to.nodeId] || 0) + 1;
            outgoingMap[e.from.nodeId] = outgoingMap[e.from.nodeId] || [];
            outgoingMap[e.from.nodeId].push(e);
          }
          const q: string[] = [];
          for (const id of Object.keys(incomingCount)) if ((incomingCount[id] || 0) === 0) q.push(id);
          const order: string[] = [];
          while (q.length) {
            const id = q.shift()!;
            order.push(id);
            const outs = outgoingMap[id] || [];
            for (const o of outs) {
              const tgt = o.to.nodeId;
              incomingCount[tgt] = Math.max(0, (incomingCount[tgt] || 0) - 1);
              if (incomingCount[tgt] === 0) q.push(tgt);
            }
          }
          for (const n of bNodes) if (!order.includes(n.id)) order.push(n.id);

          // build python code to run subgraph and collect outputs
          const PY_KEYWORDS = new Set([
            'False','None','True','and','as','assert','async','await','break','class','continue','def','del','elif','else','except','finally','for','from','global','if','import','in','is','lambda','nonlocal','not','or','pass','raise','return','try','while','with','yield'
          ]);
          function sanitizeName(name: string, idx: number) {
            let nm = (name && name.trim()) ? name.replace(/[^0-9a-zA-Z_]/g, '_') : '';
            if (!nm) nm = `arg${idx}`;
            if (/^[0-9]/.test(nm)) nm = `arg${idx}`;
            if (PY_KEYWORDS.has(nm)) nm = nm + '_';
            return nm;
          }

          // folded input param names (sanitized) mapped to inputNodes order
          const foldedInputLabels = inputNodes.map(n => (n.label || n.id));
          const foldedParamNames = foldedInputLabels.map((l: string, i: number) => sanitizeName(l, i));

          // prepare inputs array from external sources: for each inputNode, find incoming edge from external and get its source lastResult
          const inputsArray: any[] = [];
          for (const inNode of inputNodes) {
            // find an incoming edge in backup.edges where to.nodeId === inNode.id and from is external (not in bNodeIds)
            const inc = (bEdges || []).find((ee: any) => ee.to.nodeId === inNode.id && !bNodeIds.has(ee.from.nodeId));
            if (inc) {
              const src = nodes.find(n => n.id === inc.from.nodeId);
              inputsArray.push(src ? (('lastResult' in src) ? (src as any).lastResult : null) : null);
            } else {
              inputsArray.push(null);
            }
          }

          // build inner python parts
          const inner: string[] = [];
          inner.push('sub_last = {}');
          for (const nid of order) {
            const bn = bNodes.find(x => x.id === nid);
            if (!bn) continue;
            inner.push(`# Node ${bn.label || nid} (${nid})`);
            // prepare input bindings
            const inEdges = (bEdges || []).filter((ee: any) => ee.to.nodeId === nid);
            for (let i = 0; i < (bn.inputs || []).length; i++) {
              const inName = (bn.inputs && bn.inputs[i]) ? bn.inputs[i] : `arg${i}`;
              const incoming = inEdges.find((ee: any) => ee.to.portIndex === i);
              if (incoming) {
                if (bNodeIds.has(incoming.from.nodeId)) {
                  inner.push(`${inName} = sub_last.get(${JSON.stringify(incoming.from.nodeId)})`);
                } else {
                  // external source -> bind from folded param (find index in inputNodes by target?)
                  // find which folded param corresponds to this external source: match by to.nodeId == inputNode.id
                  const idx = inputNodes.findIndex(n => n.id === incoming.to.nodeId);
                  const paramVar = foldedParamNames[idx] || 'None';
                  inner.push(`${inName} = ${paramVar}`);
                }
              } else {
                inner.push(`${inName} = None`);
              }
            }
            // user code
            const userLines = (bn.code || 'res = None').split('\n');
            inner.push('try:');
            for (const l of userLines) inner.push('    ' + l);
            inner.push('    try:');
            inner.push(`        sub_last[${JSON.stringify(nid)}] = res`);
            inner.push('    except NameError:');
            inner.push(`        sub_last[${JSON.stringify(nid)}] = None`);
            inner.push('except Exception as _e:');
            inner.push(`    print('node ${nid} exception:', _e)`);
            inner.push(`    sub_last[${JSON.stringify(nid)}] = None`);
            inner.push('');
          }
          // prepare result mapping from folder outputs (outputNodes)
          inner.push('res = {}');
          for (const on of (bNodes.filter(n => n.isOutput) || [])) {
            inner.push(`try:`);
            inner.push(`    res[${JSON.stringify(on.label || on.id)}] = sub_last.get(${JSON.stringify(on.id)})`);
            inner.push('except Exception:');
            inner.push(`    res[${JSON.stringify(on.label || on.id)}] = None`);
          }
          inner.push('import json');
          inner.push('from js import setNodeResult');
          inner.push(`setNodeResult(${JSON.stringify(nodeId)}, json.dumps(res, default=str))`);

          // wrap with stdout/stderr redirection and param binding
          const wrapped = `\nimport sys\nfrom js import pushDebug\nclass _W:\n    def write(self,s):\n        try:\n            if s is None: return\n            s2 = str(s)\n            if s2.strip():\n                pushDebug(s2)\n        except Exception as e:\n            pass\n    def flush(self):\n        pass\nsys.stdout = _W()\nsys.stderr = _W()\n\ndef __fold_exec(__node_args):\n${foldedParamNames.map((p, i) => `    ${p} = __node_args[${i}]`).join('\n')}\n${inner.map(line => '    ' + line).join('\n')}\n\ntry:\n    __fold_exec(__node_args)\nexcept Exception as _e:\n    pushDebug('folded py exception: ' + str(_e))\n    raise\n`;

          try {
            try { pyodide.value.globals.set('__node_args', inputsArray); } catch (e) {}
            await pyodide.value.runPythonAsync(wrapped);
            try { (node as any).status = 'done'; } catch (e) {}
            return;
          } catch (err: any) {
            logDebug('folded run error', err?.toString ? err.toString() : err);
            try { (node as any).status = 'error'; } catch (e) {}
            return;
          }
      }
      } catch (e) { logDebug('fold-run detection error', e); }
      // skip execution if node is disabled by its folder
      try {
        if (isNodeDisabled(node)) {
          logDebug('runNode skipped (node disabled)', nodeId);
          try { (node as any).status = 'disabled'; } catch (e) {}
          return;
        }
      } catch (e) {}
      // set running status
      try { (node as any).status = 'running'; } catch (e) {}
      // gather inputs from connected edges -> source node.lastResult
      const inputs: any[] = [];
      if (node.inputs && node.inputs.length) {
        for (let i = 0; i < node.inputs.length; i++) {
          const e = edges.find(ed => ed.to.nodeId === node.id && ed.to.portIndex === i);
          if (e) {
            const src = nodes.find(n => n.id === e.from.nodeId);
            inputs.push(src ? (('lastResult' in src) ? (src as any).lastResult : null) : null);
          } else {
            inputs.push(null);
          }
        }
      }
      if (isBuiltinNode(node.category)) {
        try {
          const output = await runBuiltinNode(node, inputs, envVars);
          node.lastResult = output;
          logDebug('runBuiltinNode executed', nodeId);
          try { (node as any).status = 'done'; } catch (e) {}
        } catch (err: any) {
          logDebug('runBuiltinNode error: ' + (err?.toString ? err.toString() : String(err)));
          node.lastResult = { error: err?.message || String(err) };
          try { (node as any).status = 'error'; } catch (e) {}
        }
        return;
      }
      if (node.category === 'note') {
        node.lastResult = { type: 'note', text: (node as any).meta?.note || '' };
        try { (node as any).status = 'done'; } catch (e) {}
        return;
      }
      if (!pyReady.value) {
        logDebug('pyodide not ready yet');
        try { (node as any).status = 'idle'; } catch (e) {}
        return;
      }
      try {
        try { pyodide.value.globals.set('__node_args', inputs); } catch (e) { /* ignore */ }
        const userCode = (node as any).code || '';
        // build param name list (use provided input names or fallback arg0..)
        // sanitize parameter names: remove invalid chars and avoid Python keywords
        const PY_KEYWORDS = new Set([
          'False','None','True','and','as','assert','async','await','break','class','continue','def','del','elif','else','except','finally','for','from','global','if','import','in','is','lambda','nonlocal','not','or','pass','raise','return','try','while','with','yield'
        ]);
        const paramNames: string[] = (node.inputs && node.inputs.length) ? node.inputs.map((nm, i) => {
          let name = (nm && nm.trim()) ? nm.replace(/[^0-9a-zA-Z_]/g, '_') : '';
          if (!name) name = `arg${i}`;
          if (/^[0-9]/.test(name)) name = `arg${i}`;
          if (PY_KEYWORDS.has(name)) name = name + '_';
          return name;
        }) : [];
        const pyParts: string[] = [];
        // create a unique function wrapper so the user's code runs in a local scope
        const safeFuncName = `__node_exec_${String(node.id).replace(/[^0-9a-zA-Z_]/g, '_')}`;
        pyParts.push(`def ${safeFuncName}(__node_args):`);
        // bind params from __node_args inside the function scope
        for (let i = 0; i < paramNames.length; i++) {
          pyParts.push(`    ${paramNames[i]} = __node_args[${i}]`);
        }
        // user code (body) - expects to set variable `res` to returnable value
        const userLines = (userCode || 'res = None').split('\n');
        for (const ln of userLines) {
          pyParts.push('    ' + ln);
        }
        // ensure function returns res or None
        pyParts.push('    try:');
        pyParts.push('        return res');
        pyParts.push('    except NameError:');
        pyParts.push('        return None');

        // call the function and serialize result
        pyParts.push(`out = ${safeFuncName}(__node_args)`);
        pyParts.push('import json');
        pyParts.push('from js import setNodeResult');
        pyParts.push(`setNodeResult(${JSON.stringify(node.id)}, json.dumps(out, default=str))`);
        const inner = pyParts.join('\n');
        const wrapped = `\nimport sys\nfrom js import pushDebug, setNodeResult\nclass _W:\n    def write(self,s):\n        try:\n            if s is None: return\n            s2 = str(s)\n            if s2.strip():\n                pushDebug(s2)\n        except Exception as e:\n            pass\n    def flush(self):\n        pass\nsys.stdout = _W()\nsys.stderr = _W()\ntry:\n${inner.split('\n').map(line=> '    ' + line).join('\n')}\nexcept Exception as _e:\n    pushDebug('py exception: ' + str(_e))\n    raise\n`;
        await pyodide.value.runPythonAsync(wrapped);
        logDebug('runNode executed', nodeId);
        try { (node as any).status = 'done'; } catch (e) {}
      } catch (err: any) {
        logDebug('runNode py error: ' + (err?.toString ? err.toString() : String(err)));
        try { (node as any).status = 'error'; } catch (e) {}
      }
    }

    async function installPackages() {
      if (!pyReady.value) {
        logDebug('pyodide not ready yet');
        return;
      }
      const raw = (pyPackages.value || '').trim();
      if (!raw) {
        logDebug('no packages specified');
        return;
      }
      const list = raw.split(',').map(s => s.trim()).filter(s => !!s);
      logDebug('installing packages', list);
      try {
        const builtinPackages = ['numpy', 'pandas', 'matplotlib', 'scipy', 'sympy', 'pyarrow'];
        // ensure micropip is available in pyodide
        try {
          await pyodide.value.runPythonAsync('import micropip');
        } catch (e) {
          logDebug('micropip not present, loading via pyodide.loadPackage("micropip")');
          try {
            await pyodide.value.loadPackage('micropip');
            logDebug('micropip loaded via loadPackage');
          } catch (le) {
            logDebug('failed to load micropip via loadPackage', le?.toString ? le.toString() : le);
            throw le;
          }
        }
        const loadTargets = list.filter(pkg => builtinPackages.includes(pkg.toLowerCase()));
        if (loadTargets.length) {
          try {
            logDebug('loading pyodide builtin packages', loadTargets);
            await pyodide.value.loadPackage(loadTargets);
          } catch (builtinErr: any) {
            logDebug('loadPackage warning: ' + (builtinErr?.toString ? builtinErr.toString() : String(builtinErr)));
          }
        }
        // use micropip to install; supports wheel URLs and package names
        const pipTargets = list.filter(pkg => !builtinPackages.includes(pkg.toLowerCase()) || /^https?:/i.test(pkg));
        if (pipTargets.length) {
          const pyList = JSON.stringify(pipTargets);
          const code = `import micropip\nawait micropip.install(${pyList}, keep_going=True)`;
          await pyodide.value.runPythonAsync(code);
        }
        logDebug('installPackages success', list);
      } catch (err: any) {
        logDebug('installPackages error: ' + (err?.toString ? err.toString() : String(err)));
        logDebug('installPackages hint: 优先使用 Pyodide 支持的纯 Python 包，像 numpy/pandas 可直接写包名，其它第三方包建议提供 wheel URL。');
      }
    }

    // Execute entire graph in topological order
    async function executeGraph() {
      try {
        // Build maps of incoming counts and outgoing edges, but ignore disabled nodes
        const incomingCount: Record<string, number> = {};
        const outgoingMap: Record<string, Array<typeof edges[0]>> = {};
        // consider only enabled nodes
        const enabledNodeIds = new Set(nodes.filter(n => !isNodeDisabled(n)).map(n => n.id));
        for (const id of enabledNodeIds) { incomingCount[id] = 0; outgoingMap[id] = []; }
        for (const e of edges) {
          // skip edges involving disabled nodes
          if (!enabledNodeIds.has(e.from.nodeId) || !enabledNodeIds.has(e.to.nodeId)) continue;
          incomingCount[e.to.nodeId] = (incomingCount[e.to.nodeId] || 0) + 1;
          outgoingMap[e.from.nodeId] = outgoingMap[e.from.nodeId] || [];
          outgoingMap[e.from.nodeId].push(e);
        }

        // mark statuses: disabled nodes flagged, enabled nodes reset to idle before execution
        try {
          for (const n of nodes) {
            if (isNodeDisabled(n)) { try { (n as any).status = 'disabled'; } catch (e) {} }
            else { try { (n as any).status = 'idle'; } catch (e) {} }
          }
        } catch (e) {}

        // determine starting nodes (isInit === true). If none, fall back to nodes with zero incoming edges.
        // determine starting nodes (isInit === true) among enabled nodes. If none, fall back to enabled nodes with zero incoming edges.
        const startIds = nodes.filter(n => enabledNodeIds.has(n.id) && (n as any).isInit).map(n => n.id);
        const initial = startIds.length ? startIds : nodes.filter(n => enabledNodeIds.has(n.id) && (incomingCount[n.id] || 0) === 0).map(n => n.id);

        // compute reachable set from initial nodes so we know when we're done
        const reachable = new Set<string>();
        const stack = [...initial];
        while (stack.length) {
          const id = stack.pop()!;
          if (reachable.has(id)) continue;
          reachable.add(id);
          const outs = outgoingMap[id] || [];
          for (const o of outs) {
            if (!reachable.has(o.to.nodeId)) stack.push(o.to.nodeId);
          }
        }

        if (reachable.size === 0) {
          logDebug('executeGraph: no reachable nodes to run');
          return;
        }

        logDebug('executeGraph starting from', Array.from(initial), 'reachable count', reachable.size);

        // working copy of incoming counts for reachable nodes only
        const pending = Object.assign({}, incomingCount);

        // spawn tasks and track completion
        let completed = 0;
        const total = reachable.size;
        const started = new Set<string>();

        function spawn(id: string) {
          if (started.has(id)) return;
          started.add(id);
          (async () => {
            try {
              await runNode(id);
            } catch (e) {
              logDebug('runNode failed for', id, e?.toString ? e.toString() : e);
            }
            // propagate outputs to downstream nodes
            const src = nodes.find(n => n.id === id);
            const value = src && ('lastResult' in src) ? (src as any).lastResult : null;
            const outs = outgoingMap[id] || [];
            for (const o of outs) {
              const tgt = o.to.nodeId;
              try {
                // decrease pending count and set placeholder for input (runNode will read lastResult from source nodes)
                pending[tgt] = Math.max(0, (pending[tgt] || 0) - 1);
                if (pending[tgt] === 0) {
                  // schedule run for target
                  spawn(tgt);
                }
              } catch (e) {}
            }
            completed++;
            if (completed >= total) {
              logDebug('executeGraph finished');
            }
          })();
        }

        // start from initial nodes
        for (const id of initial) {
          if (reachable.has(id)) spawn(id);
        }

        // wait until all reachable nodes complete
        await new Promise<void>((resolve) => {
          const check = () => {
            if (completed >= total) return resolve();
            setTimeout(check, 30);
          };
          check();
        });

      } catch (e) {
        logDebug('executeGraph error', e?.toString ? e.toString() : e);
      }
    }

    // Context menu state and presets
    const contextMenu = reactive({ visible: false, x: 0, y: 0, catIndex: 0, pageX: 0, pageY: 0 });

    // hover submenu state when hovering a category in the context menu
    const submenu = reactive<{ visible: boolean; x: number; y: number; items: any[]; hideTimeout?: any }>({ visible: false, x: 0, y: 0, items: [] });

    const categories = [
      {
        key: 'inputs',
        label: '输入',
        items: [
          { key: 'const', label: '常量', desc: '数值常量' },
          { key: 'text', label: '文本', desc: '文本输出' }
        ]
      },
      {
        key: 'math',
        label: '运算',
        items: [
          { key: 'add', label: '加法', desc: '两个输入相加' },
          { key: 'mul', label: '乘法', desc: '两个输入相乘' }
        ]
      },
      {
        key: 'outputs',
        label: '输出',
        items: [{ key: 'print', label: '显示', desc: '输出至控制台' }]
      },
      {
        key: 'knowledge',
        label: '知识库',
        items: KNOWLEDGE_NODE_PRESETS.map(item => ({
          key: item.key,
          label: item.label,
          desc: item.desc
        }))
      },
      {
        key: 'components',
        label: '组件',
        items: [{ key: 'note', label: '注释便签', desc: '用于说明、注释和设计备注' }]
      }
    ];

    // add folder option in context menu
    categories.splice(0, categories.length, ...NODE_LIBRARY_SECTIONS.map(section => ({ ...section, items: [...section.items] })));
    categories.push({ key: 'group', label: '文件夹', items: [{ key: 'folder', label: '新建文件夹', desc: '在编辑区创建容器，用于组织节点' }] });

    function closeContextMenu() {
      contextMenu.visible = false;
      submenu.visible = false;
    }

    function onContextMenuArea(e: PointerEvent) {
      // deprecated: handled by global contextmenu listener
    }

    function createNodeByPreset(item: { key: string; label: string; desc?: string }, x: number, y: number) {
      const cat = item.key;
      if (item.key === 'folder' || item.key === 'group') {
        const w = 360; const h = 220;
        folders.push({ id: `folder_${Date.now()}`, x, y, w, h, label: item.label || 'Folder', children: [] });
        return;
      }
      const presetNode = createNodeFromPreset(item.key, `node_${nodeSeq++}`, x, y);
      if (presetNode) {
        if (item.label && item.key !== 'note') presetNode.label = item.label;
        nodes.push(presetNode);
        rebuildNodeModules();
        return;
      }

      if (isKnowledgeNode(cat)) {
        nodes.push(createKnowledgeNode(cat, `node_${nodeSeq++}`, x, y));
        rebuildNodeModules();
        return;
      }
      if (cat === 'note') {
        nodes.push({
          id: `node_${nodeSeq++}`,
          x,
          y,
          label: item.label || '注释便签',
          category: 'note',
          inputs: [],
          outputs: [],
          inputTypes: [],
          outputTypes: [],
          code: '',
          lastResult: null,
          color: '#F4C95D',
          meta: {
            note: '双击右侧面板可编辑便签内容',
            template: { kind: 'note', version: '1.0.0' },
            community: { shareId: '', visibility: 'private', tags: ['note'] }
          }
        });
        rebuildNodeModules();
        return;
      }

      let inputs: string[] = [];
      let outputs: string[] = [];
      if (cat === 'const') { inputs = []; outputs = ['value']; }
      else if (cat === 'text') { inputs = []; outputs = ['text']; }
      else if (cat === 'add' || cat === 'mul') { inputs = ['a', 'b']; outputs = ['res']; }
      else if (cat === 'print') { inputs = ['in']; outputs = []; }
      nodes.push({
        id: `node_${nodeSeq++}`,
        x,
        y,
        label: item.label,
        category: cat,
        inputs,
        outputs,
        inputTypes: inputs.map(() => 'Any'),
        outputTypes: outputs.map(() => 'Any'),
        code: '',
        lastResult: null,
        meta: {
          template: { kind: 'built-in', version: '1.0.0' },
          community: { shareId: '', visibility: 'private', tags: [cat] }
        }
      });
      rebuildNodeModules();
    }

    function addPresetNode(item: { key: string; label: string; desc?: string }) {
      const area = areaRef.value!;
      const rect = area.getBoundingClientRect();
      // ensure created node is inset from editor edges
      const margin = 48;
      const nodeW = NODE_W;
      const nodeRows = 1;
      const nodeH = headerHeight + BODY_PADDING * 2 + nodeRows * rowHeight + Math.max(0, nodeRows - 1) * rowGap;
      const x = clamp(contextMenu.x, margin, Math.max(margin, rect.width - nodeW - margin));
      const y = clamp(contextMenu.y, margin, Math.max(margin, rect.height - nodeH - margin));
      createNodeByPreset(item, x, y);
      closeContextMenu();
    }

    function onFolderPointerDown(e: PointerEvent, folder: any) {
      // select the folder
      selectedIds.value = [folder.id];
      // If click landed on the folder container itself (not a child node), start folder drag.
      try {
        if (e.target === e.currentTarget) {
          interactions.handleFolderPointerDown(e, folder);
        }
      } catch (er) {}
    }

    // Close context menu when clicking outside or pressing Escape
    function onDocClick(e: MouseEvent) {
      if (contextMenu.visible) {
        closeContextMenu();
      }
    }

    function onHoverCategory(catKey: string, e: MouseEvent) {
      // find category and compute submenu position near the menu
      const cat = categories.find(c => c.key === catKey);
      if (!cat) return;
      // menu origin (contextMenu.pageX/Y) plus offset to align submenu
      const baseX = contextMenu.pageX;
      const baseY = contextMenu.pageY;
      // approximate placement: submenu to the right of category list
      const offsetX = 220; // matches min-width of category column
      const mouseY = e.clientY;
      submenu.items = cat.items || [];
      submenu.x = baseX + offsetX;
      submenu.y = Math.max(baseY, mouseY - 12);
      // show with slight delay for smoother UX
      if (submenu.hideTimeout) { clearTimeout(submenu.hideTimeout); submenu.hideTimeout = undefined; }
      submenu.visible = true;
    }

    function onLeaveCategory() {
      // schedule hide to allow entering submenu
      if (submenu.hideTimeout) clearTimeout(submenu.hideTimeout);
      submenu.hideTimeout = setTimeout(() => { submenu.visible = false; submenu.hideTimeout = undefined; }, 220);
    }

    function cancelHideSubmenu() {
      if (submenu.hideTimeout) { clearTimeout(submenu.hideTimeout); submenu.hideTimeout = undefined; }
    }

    function scheduleHideSubmenu() {
      if (submenu.hideTimeout) clearTimeout(submenu.hideTimeout);
      submenu.hideTimeout = setTimeout(() => { submenu.visible = false; submenu.hideTimeout = undefined; }, 180);
    }

    function onDocKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && contextMenu.visible) {
        closeContextMenu();
      }
    }

    onMounted(async () => {
      window.addEventListener('click', onDocClick);
      window.addEventListener('keydown', onDocKey);
      window.addEventListener('contextmenu', onGlobalContextMenu);
      const restored = await restoreInitialWorkspace();
      if (!restored) {
        const n1 = { id: `node_${nodeSeq++}`, x: 120, y: 120, label: 'Const A', category: 'const', inputs: [], outputs: ['value'], inputTypes: [], outputTypes: ['Any'], code: 'res = 2', lastResult: null, isInit: true };
        const n2 = { id: `node_${nodeSeq++}`, x: 120, y: 240, label: 'Const B', category: 'const', inputs: [], outputs: ['value'], inputTypes: [], outputTypes: ['Any'], code: 'res = 3', lastResult: null, isInit: true };
        const mul = { id: `node_${nodeSeq++}`, x: 380, y: 180, label: 'Multiply', category: 'mul', inputs: ['a','b'], outputs: ['res'], inputTypes: ['Any','Any'], outputTypes: ['Any'], code: 'res = a * b', lastResult: null };
        const pr = { id: `node_${nodeSeq++}`, x: 620, y: 180, label: 'Print', category: 'print', inputs: ['in'], outputs: [], inputTypes: ['Any'], outputTypes: [], code: 'print(res)', lastResult: null };
        nodes.push(n1, n2, mul, pr);
        edges.push({ id: `edge_${nodeSeq++}_1`, from: { nodeId: n1.id, portIndex: 0 }, to: { nodeId: mul.id, portIndex: 0 } });
        edges.push({ id: `edge_${nodeSeq++}_2`, from: { nodeId: n2.id, portIndex: 0 }, to: { nodeId: mul.id, portIndex: 1 } });
        edges.push({ id: `edge_${nodeSeq++}_3`, from: { nodeId: mul.id, portIndex: 0 }, to: { nodeId: pr.id, portIndex: 0 } });
        folders.push({ id: `folder_1`, x: 340, y: 160, w: 360, h: 160, label: '示例分组', children: [mul.id, pr.id] });
      }
      // load pyodide in background
      loadPyodideAndInit().catch(e => logDebug('loadPyodide failed', e?.toString ? e.toString() : e));
      // init node module list
      loadNodeTemplates();
      rebuildNodeModules();
      refreshCloudModuleCount();
    });

    watch(nodes, () => queuePersistWorkspace(), { deep: true });
    watch(edges, () => queuePersistWorkspace(), { deep: true });
    watch(folders, () => queuePersistWorkspace(), { deep: true });
    watch(envVars, () => queuePersistWorkspace(), { deep: true });
    watch(() => [moduleMeta.name, moduleMeta.description, moduleMeta.requires], () => queuePersistWorkspace(), { deep: true });

    onBeforeUnmount(() => {
      if (workspaceSaveTimer) clearTimeout(workspaceSaveTimer);
      window.removeEventListener('click', onDocClick);
      window.removeEventListener('keydown', onDocKey);
      window.removeEventListener('contextmenu', onGlobalContextMenu);
      window.removeEventListener('pointermove', onPointerMoveWindow);
      window.removeEventListener('pointerup', onPointerUpWindow);
    });

    // selectedNode changes are handled inside RightSidebar component (editor is encapsulated there)

    const showDebug = false;

    function clamp(v: number, a: number, b: number) {
      return Math.max(a, Math.min(b, v));
    }

    function onGlobalContextMenu(e: MouseEvent) {
      const area = areaRef.value;
      if (!area) return;
      // only open when right-click inside the editor area
      if (!(e.target instanceof Element) || !area.contains(e.target as Element)) return;
      e.preventDefault();
      const rect = area.getBoundingClientRect();
      const menuW = 320;
      const menuH = 360;
      // clamp to editor area bounds (page coordinates)
      const px = clamp(e.clientX, rect.left + 8, Math.max(rect.left + 8, rect.right - menuW - 8));
      const py = clamp(e.clientY, rect.top + 8, Math.max(rect.top + 8, rect.bottom - menuH - 8));
      contextMenu.pageX = px;
      contextMenu.pageY = py;
      // also keep relative coordinates if needed
      contextMenu.x = px - rect.left;
      contextMenu.y = py - rect.top;
      contextMenu.catIndex = 0;
      contextMenu.visible = true;
      // ensure submenu hidden initially
      submenu.visible = false;
    }

    function addNode() {
      const area = areaRef.value;
      const margin = 48;
      if (area) {
        const rect = area.getBoundingClientRect();
        const centerX = rect.width / 2 - NODE_W / 2 + (nodes.length % 5) * 20;
        const defaultH = headerHeight + BODY_PADDING * 2 + rowHeight; // approximate default node height
        const centerY = rect.height / 2 - defaultH / 2 + Math.floor(nodes.length / 5) * 20;
        const x = clamp(centerX, margin, Math.max(margin, rect.width - NODE_W - margin));
        const y = clamp(centerY, margin, Math.max(margin, rect.height - defaultH - margin));
        nodes.push({ id: `node_${nodeSeq++}`, x, y, label: `节点 ${nodeSeq - 1}`, inputs: [], outputs: [], inputTypes: [], outputTypes: [], code: '', lastResult: null });
        rebuildNodeModules();
      } else {
        nodes.push({ id: `node_${nodeSeq++}`, x: 100, y: 100, label: `节点 ${nodeSeq - 1}`, inputs: [], outputs: [], inputTypes: [], outputTypes: [], code: '', lastResult: null });
        rebuildNodeModules();
      }
    }

    function clearAll() {
      nodes.splice(0, nodes.length);
      edges.splice(0, edges.length);
    }

    function exportModel() {
      const model = { nodes: JSON.parse(JSON.stringify(nodes)), edges: JSON.parse(JSON.stringify(edges)) };
      // 打印到控制台，可按需展示到弹窗
      console.log('node-editor model', model);
      alert(JSON.stringify(model, null, 2));
    }

    // export entire graph as a single Python program and trigger download
    function exportPython() {
      try {
        // only include enabled nodes
        const enabledNodes = nodes.filter(n => !isNodeDisabled(n));
        const enabledIds = new Set(enabledNodes.map(n => n.id));

        // build edge maps restricted to enabled nodes
        const incomingCount: Record<string, number> = {};
        const outgoingMap: Record<string, Array<typeof edges[0]>> = {};
        const incomingEdgesMap: Record<string, Array<typeof edges[0]>> = {};
        for (const id of enabledNodes.map(n => n.id)) { incomingCount[id] = 0; outgoingMap[id] = []; incomingEdgesMap[id] = []; }
        for (const e of edges) {
          if (!enabledIds.has(e.from.nodeId) || !enabledIds.has(e.to.nodeId)) continue;
          incomingCount[e.to.nodeId] = (incomingCount[e.to.nodeId] || 0) + 1;
          outgoingMap[e.from.nodeId] = outgoingMap[e.from.nodeId] || [];
          outgoingMap[e.from.nodeId].push(e);
          incomingEdgesMap[e.to.nodeId] = incomingEdgesMap[e.to.nodeId] || [];
          incomingEdgesMap[e.to.nodeId].push(e);
        }

        // topological order (Kahn)
        const q: string[] = [];
        for (const id of Object.keys(incomingCount)) if ((incomingCount[id] || 0) === 0) q.push(id);
        const order: string[] = [];
        while (q.length) {
          const id = q.shift()!;
          order.push(id);
          const outs = outgoingMap[id] || [];
          for (const o of outs) {
            const tgt = o.to.nodeId;
            incomingCount[tgt] = Math.max(0, (incomingCount[tgt] || 0) - 1);
            if (incomingCount[tgt] === 0) q.push(tgt);
          }
        }

        // fallback: include enabled nodes not in order (isolated cycles etc.)
        for (const n of enabledNodes) if (!order.includes(n.id)) order.push(n.id);

        const lines: string[] = [];
        // include module metadata if present
        try {
          if (moduleMeta.name) lines.push(`# Module: ${moduleMeta.name}`);
          if (moduleMeta.description) lines.push(`# Description: ${moduleMeta.description}`);
          if (moduleMeta.requires) lines.push(`# Requires: ${moduleMeta.requires}`);
        } catch (e) {}
        lines.push('# Generated Python program from node-editor');
        lines.push('');
        lines.push('lastResult = {}');
        lines.push('');

        for (const nid of order) {
          const node = nodes.find(n => n.id === nid);
          if (!node) continue;
          lines.push(`# Node ${node.label || nid} (${nid})`);
          // include optional coords and color as comments for restore
          try {
            if (typeof (node as any).x === 'number' && typeof (node as any).y === 'number') {
              lines.push(`# coords: ${Math.floor((node as any).x)},${Math.floor((node as any).y)}`);
            }
          } catch (e) {}
          try {
            const col = (node as any).color || nodeCategoryColor(node.category);
            if (col) lines.push(`# color: ${col}`);
          } catch (e) {}
          try {
            if ((node as any).isOutput) lines.push(`# output: true`);
          } catch (e) {}
          try {
            if ((node as any).isInit) lines.push(`# init: true`);
          } catch (e) {}
          // prepare input bindings
          const inputs = node.inputs || [];
          for (let i = 0; i < inputs.length; i++) {
            const inName = (inputs[i] && inputs[i].trim()) ? inputs[i].trim() : `arg${i}`;
            const incoming = (incomingEdgesMap[nid] || []).find(e => e.to.portIndex === i);
            if (incoming) {
              lines.push(`${inName} = lastResult.get(${JSON.stringify(incoming.from.nodeId)})`);
            } else {
              lines.push(`${inName} = None`);
            }
          }
          // user code wrapped to capture exceptions and set lastResult
          const userCode = (node as any).code || 'res = None';
          lines.push('try:');
          const userLines = userCode.split('\n');
          for (const l of userLines) lines.push('    ' + l);
          lines.push(`    try:`);
          lines.push(`        lastResult[${JSON.stringify(nid)}] = res`);
          lines.push('    except NameError:');
          lines.push(`        lastResult[${JSON.stringify(nid)}] = None`);
          lines.push('except Exception as _e:');
          lines.push(`    print('node ${nid} exception:', _e)`);
          lines.push(`    lastResult[${JSON.stringify(nid)}] = None`);
          lines.push('');
        }

        const code = lines.join('\n');
        const blob = new Blob([code], { type: 'text/x-python' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const name = `graph_export_${Date.now()}.py`;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(url); try { a.remove(); } catch (e) {} }, 5000);
      } catch (e) { logDebug('exportPython error', e); }
    }

    // file input ref and import handler
    const fileInputRef = ref<HTMLInputElement | null>(null);
    const nodeTemplateInputRef = ref<HTMLInputElement | null>(null);

    function handleImportFile(e: Event) {
      try {
        const inp = e.target as HTMLInputElement;
        if (!inp || !inp.files || inp.files.length === 0) return;
        const f = inp.files[0];
        const reader = new FileReader();
        reader.onload = () => {
          const text = String(reader.result || '');
          importPython(text);
          try { inp.value = ''; } catch (e) {}
        };
        reader.readAsText(f);
      } catch (e) { logDebug('handleImportFile error', e); }
    }

    function openFileDialog() {
      try {
        logDebug('openFileDialog invoked');
        if (fileInputRef.value && fileInputRef.value) {
          fileInputRef.value.click();
        } else {
          logDebug('openFileDialog: fileInputRef missing');
        }
      } catch (e) { logDebug('openFileDialog error', e); }
    }

    function openNodeTemplateDialog() {
      try {
        if (nodeTemplateInputRef.value) nodeTemplateInputRef.value.click();
      } catch (e) { logDebug('openNodeTemplateDialog error', e); }
    }

    function serializeNodeTemplate(node: Node) {
      const plain = JSON.parse(JSON.stringify(node));
      if (plain.resources) {
        plain.resources = plain.resources.map((item: any) => ({
          id: item.id,
          name: item.name,
          kind: item.kind,
          size: item.size,
          lastModified: item.lastModified
        }));
      }
      plain.meta = plain.meta || {};
      plain.meta.community = plain.meta.community || {
        shareId: '',
        author: '',
        summary: '',
        tags: [],
        visibility: 'private',
        version: '1.0.0',
        downloads: 0,
        likes: 0
      };
      return plain;
    }

    function createTemplatePayload(node: Node) {
      return {
        id: `local_${node.id}_${Date.now()}`,
        kind: 'local',
        version: '1.0.0',
        name: node.label || node.id,
        description: node.category === 'note' ? 'Canvas note component' : `Saved node template for ${node.label || node.id}`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        snapshot: serializeNodeTemplate(node),
        community: {
          shareId: '',
          slug: '',
          author: '',
          title: node.label || node.id,
          summary: '',
          tags: [node.category || 'custom'],
          cover: '',
          visibility: 'private',
          stats: { downloads: 0, likes: 0, forks: 0 }
        }
      };
    }

    function persistNodeTemplates() {
      try {
        localStorage.setItem(nodeTemplateStorageKey, JSON.stringify(savedNodeTemplates.value));
      } catch (e) { logDebug('persistNodeTemplates error', e); }
    }

    function serializeWorkspace() {
      return {
        id: `workspace_${moduleMeta.name || 'default'}`,
        name: moduleMeta.name || 'Untitled Workspace',
        description: moduleMeta.description || '',
        requires: moduleMeta.requires || '',
        updatedAt: new Date().toISOString(),
        stats: {
          nodes: nodes.length,
          edges: edges.length,
          folders: folders.length
        },
        graph: {
          nodes: JSON.parse(JSON.stringify(nodes)),
          edges: JSON.parse(JSON.stringify(edges)),
          folders: JSON.parse(JSON.stringify(folders)),
          envVars: JSON.parse(JSON.stringify(envVars))
        }
      };
    }

    function slugify(value: string) {
      return String(value || 'tokenflow-module')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 80) || `tokenflow-module-${Date.now()}`;
    }

    function persistWorkspace() {
      try {
        const current = serializeWorkspace();
        const raw = localStorage.getItem(workspaceStorageKey);
        const items = raw ? JSON.parse(raw) : [];
        const next = Array.isArray(items) ? items.filter((item: any) => item.id !== current.id) : [];
        next.unshift(current);
        localStorage.setItem(workspaceStorageKey, JSON.stringify(next.slice(0, 24)));
      } catch (e) { logDebug('persistWorkspace error', e); }
    }

    function queuePersistWorkspace() {
      if (workspaceSaveTimer) clearTimeout(workspaceSaveTimer);
      workspaceSaveTimer = setTimeout(() => {
        persistWorkspace();
      }, 250);
    }

    function loadNodeTemplates() {
      try {
        const raw = localStorage.getItem(nodeTemplateStorageKey);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) savedNodeTemplates.value = parsed;
      } catch (e) { logDebug('loadNodeTemplates error', e); }
    }

    function instantiateTemplate(snapshot: any, x: number, y: number) {
      const copy = JSON.parse(JSON.stringify(snapshot || {}));
      const newNode: Node = {
        id: `node_${nodeSeq++}`,
        x,
        y,
        label: copy.label || 'Imported Node',
        category: copy.category,
        inputs: copy.inputs || [],
        outputs: copy.outputs || [],
        inputTypes: copy.inputTypes || [],
        outputTypes: copy.outputTypes || [],
        code: copy.code || '',
        lastResult: null,
        isInit: !!copy.isInit,
        isOutput: !!copy.isOutput,
        color: copy.color,
        status: 'idle',
        meta: copy.meta || {},
        resources: copy.resources || []
      };
      nodes.push(newNode);
      rebuildNodeModules();
    }

    function importSavedTemplate(template: any) {
      const area = areaRef.value;
      if (!area) return;
      const rect = area.getBoundingClientRect();
      const x = clamp(rect.width / 2 - NODE_W / 2 + (nodes.length % 4) * 20, 48, Math.max(48, rect.width - NODE_W - 48));
      const y = clamp(120 + Math.floor(nodes.length / 4) * 20, 48, Math.max(48, rect.height - 220));
      instantiateTemplate(template.snapshot || template, x, y);
    }

    function applyWorkflowTemplate(template: any) {
      const area = areaRef.value;
      if (!area || !template?.nodes) return;
      const rect = area.getBoundingClientRect();
      const baseX = clamp(rect.width / 2 - 420, 48, Math.max(48, rect.width - 900));
      const baseY = clamp(rect.height / 2 - 120, 80, Math.max(80, rect.height - 420));
      const created: string[] = [];

      template.nodes.forEach((item: any) => {
        const node = createNodeFromPreset(item.presetKey, `node_${nodeSeq++}`, baseX + Number(item.dx || 0), baseY + Number(item.dy || 0));
        if (!node) return;
        if (item.label) node.label = item.label;
        if (typeof item.code === 'string') node.code = item.code;
        if (item.meta) node.meta = { ...(node.meta || {}), ...item.meta };
        if (item.isInit != null) (node as any).isInit = !!item.isInit;
        if (item.isOutput != null) (node as any).isOutput = !!item.isOutput;
        nodes.push(node);
        created.push(node.id);
      });

      template.edges?.forEach((edge: any, index: number) => {
        const fromId = created[edge.from];
        const toId = created[edge.to];
        if (!fromId || !toId) return;
        edges.push({
          id: `edge_tpl_${Date.now()}_${index}`,
          from: { nodeId: fromId, portIndex: Number(edge.fromPort || 0) },
          to: { nodeId: toId, portIndex: Number(edge.toPort || 0) }
        });
      });

      rebuildNodeModules();
    }

    function saveSelectedNodeTemplate() {
      const node = selectedNode.value;
      if (!node) return;
      const payload = createTemplatePayload(node);
      savedNodeTemplates.value = [payload, ...savedNodeTemplates.value.filter(item => item.name !== payload.name)];
      persistNodeTemplates();
      logDebug('saveSelectedNodeTemplate', payload.name);
    }

    function deleteSavedTemplate(id: string) {
      savedNodeTemplates.value = savedNodeTemplates.value.filter(item => item.id !== id);
      persistNodeTemplates();
    }

    function handleImportNodeTemplateFile(e: Event) {
      try {
        const input = e.target as HTMLInputElement;
        if (!input.files?.length) return;
        const file = input.files[0];
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const parsed = JSON.parse(String(reader.result || '{}'));
            const list = Array.isArray(parsed) ? parsed : [parsed];
            list.forEach(template => {
              if (template?.snapshot) savedNodeTemplates.value.unshift(template);
              else savedNodeTemplates.value.unshift({ ...createTemplatePayload(template), snapshot: template });
            });
            persistNodeTemplates();
          } catch (err) {
            logDebug('handleImportNodeTemplateFile parse error', err);
          } finally {
            input.value = '';
          }
        };
        reader.readAsText(file);
      } catch (e2) { logDebug('handleImportNodeTemplateFile error', e2); }
    }

    function loadWorkspaceSnapshot(snapshot: any) {
      if (!snapshot) return;
      const graph = snapshot.graph || snapshot.content?.graph || {};
      nodes.splice(0, nodes.length, ...JSON.parse(JSON.stringify(graph.nodes || [])));
      edges.splice(0, edges.length, ...JSON.parse(JSON.stringify(graph.edges || [])));
      folders.splice(0, folders.length, ...JSON.parse(JSON.stringify(graph.folders || [])));
      envVars.splice(0, envVars.length, ...JSON.parse(JSON.stringify(graph.envVars || [])));
      moduleMeta.name = snapshot.name || snapshot.content?.name || 'TokenFlow Workspace';
      moduleMeta.description = snapshot.description || snapshot.content?.description || '';
      moduleMeta.requires = snapshot.requires || snapshot.content?.requires || '';
      selectedIds.value = [];
      nodeSeq = Math.max(1, nodes.length + 1);
      rebuildNodeModules();
    }

    async function refreshCloudModuleCount() {
      const token = getStoredAccessToken();
      if (!token) return;
      try {
        const items = await fetchMyPluginLibrary({ plugin_type: 'module' }, token);
        cloudModuleCount.value = items.length;
      } catch (e) {
        logDebug('refreshCloudModuleCount error', e?.toString ? e.toString() : e);
      }
    }

    async function saveWorkspaceToPersonalModule() {
      const token = getStoredAccessToken();
      if (!token) {
        window.$message?.warning('请先登录后再保存到个人模块库');
        return;
      }
      try {
        await uploadPlugin({
          name: moduleMeta.name || 'TokenFlow Workspace',
          slug: `${slugify(moduleMeta.name || 'workspace')}-${Date.now()}`,
          summary: moduleMeta.description || 'Saved from workspace sidebar',
          category: 'workspace',
          plugin_type: 'module',
          author_name: 'TokenFlow User',
          tags: ['workspace', 'personal-module'],
          source: { channel: 'workspace-sidebar', mode: 'personal-module' },
          route_info: { saved_from: 'left-sidebar', requires: moduleMeta.requires || '' },
          library_kind: 'personal',
          workspace_snapshot: serializeWorkspace(),
          is_public: false
        }, token);
        window.$message?.success('已保存到个人模块库');
        refreshCloudModuleCount();
      } catch (e: any) {
        window.$message?.error(e?.message || '保存到个人模块库失败');
      }
    }

    async function uploadSelectedNodeTemplate() {
      const token = getStoredAccessToken();
      const node = selectedNode.value;
      if (!token) {
        window.$message?.warning('请先登录后再上传到个人节点库');
        return;
      }
      if (!node) return;
      try {
        await uploadPlugin({
          name: node.label || node.id,
          slug: `${slugify(node.label || node.id)}-${Date.now()}`,
          summary: `Node template uploaded from ${moduleMeta.name || 'workspace'}`,
          category: node.category || 'custom',
          plugin_type: 'node-template',
          author_name: 'TokenFlow User',
          tags: [node.category || 'custom', 'personal-node'],
          source: { channel: 'node-inspector', workspace: moduleMeta.name || '' },
          route_info: { node_id: node.id, node_kind: node.meta?.nodeKind || 'custom' },
          library_kind: 'personal',
          node_template_snapshot: serializeNodeTemplate(node),
          is_public: false
        }, token);
        window.$message?.success('已上传到个人节点库');
      } catch (e: any) {
        window.$message?.error(e?.message || '上传节点模板失败');
      }
    }

    async function restoreInitialWorkspace() {
      const pending = consumePendingWorkspaceImport();
      if (pending && route.query.pending === '1') {
        loadWorkspaceSnapshot(pending);
        return true;
      }

      if (route.query.module && route.query.source === 'local') {
        const target = loadWorkspaceSnapshots().find(item => item.id === route.query.module);
        if (target) {
          loadWorkspaceSnapshot(target);
          return true;
        }
      }

      if (route.query.cloudPlugin) {
        const token = getStoredAccessToken();
        if (!token) return false;
        const list = await fetchMyPluginLibrary({ plugin_type: 'module' }, token);
        const target = list.find(item => String(item.id) === String(route.query.cloudPlugin));
        if (target?.workspace_snapshot) {
          loadWorkspaceSnapshot(target.workspace_snapshot);
          return true;
        }
      }

      if (route.query.workspaceId) {
        const token = getStoredAccessToken();
        if (!token) return false;
        const workspace = await fetchWorkspaceById(Number(route.query.workspaceId), token);
        if (workspace?.content) {
          loadWorkspaceSnapshot(workspace.content);
          return true;
        }
      }

      return false;
    }

    // parse exported python and restore nodes + edges
    function importPython(text: string) {
      try {
        const lines = text.split(/\r?\n/);
        // parse top-of-file module metadata comments before first node block
        try {
          let firstNodeIdx = lines.findIndex(l => /^#\s*Node\s+/i.test(l));
          if (firstNodeIdx === -1) firstNodeIdx = 0;
          for (let i = 0; i < firstNodeIdx; i++) {
            const l = lines[i];
            const m1 = l.match(/^#\s*Module:\s*(.+)$/i);
            if (m1) moduleMeta.name = m1[1].trim();
            const m2 = l.match(/^#\s*Description:\s*(.+)$/i);
            if (m2) moduleMeta.description = m2[1].trim();
            const m3 = l.match(/^#\s*Requires:\s*(.+)$/i);
            if (m3) { moduleMeta.requires = m3[1].trim(); pyPackages.value = m3[1].trim(); }
          }
          if (moduleMeta.name) logDebug('importPython: module meta loaded', moduleMeta);
        } catch (e) { logDebug('importPython meta parse error', e); }
        const blocks: Array<{ header: string; lines: string[] }> = [];
        let cur: { header: string; lines: string[] } | null = null;
        for (const ln of lines) {
          const m = ln.match(/^#\s*Node\s*(.*)\(([^)]+)\)\s*$/);
          if (m) {
            if (cur) blocks.push(cur);
            cur = { header: ln, lines: [] };
          } else {
            if (cur) cur.lines.push(ln);
          }
        }
        if (cur) blocks.push(cur);

        if (blocks.length === 0) {
          logDebug('importPython: no node blocks found');
          return;
        }

        // mapping from exported id -> new node id
        const idMap: Record<string, string> = {};
        const createdNodes: any[] = [];

        // first pass: create nodes with code and coords
        for (const b of blocks) {
          const mh = b.header.match(/^#\s*Node\s*(.*)\(([^)]+)\)\s*$/);
          if (!mh) continue;
          const label = mh[1].trim();
          const expId = mh[2].trim();
          // look for coords and color comments in block lines like: # coords: x,y  and # color: #rrggbb
          let x = 100 + (createdNodes.length % 6) * 20;
          let y = 100 + Math.floor(createdNodes.length / 6) * 20;
          let color: string | undefined = undefined;
          let isOutputFlag = false;
          let isInitFlag = false;
          for (const l of b.lines) {
            const cm = l.match(/^#\s*coords:\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*$/i);
            if (cm) { x = Number(cm[1]); y = Number(cm[2]); }
            const colm = l.match(/^#\s*color:\s*(#?[A-Za-z0-9#().,-]+)\s*$/i);
            if (colm) { color = colm[1]; }
            const om = l.match(/^#\s*output:\s*(true|1|yes)\s*$/i);
            if (om) { isOutputFlag = true; }
            const im = l.match(/^#\s*init:\s*(true|1|yes)\s*$/i);
            if (im) { isInitFlag = true; }
            if (cm) break;
          }
          // extract input var lines before first 'try:'
          const inputVars: string[] = [];
          const inputSources: Array<string | null> = [];
          for (const l of b.lines) {
            const im = l.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*lastResult\.get\((['"])(.+?)\2\)\s*$/);
            if (im) { inputVars.push(im[1]); inputSources.push(im[3]); continue; }
            const inone = l.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*None\s*$/);
            if (inone) { inputVars.push(inone[1]); inputSources.push(null); continue; }
            // stop collecting when hitting 'try:' line
            if (/^\s*try\s*:\s*$/.test(l)) break;
          }
          // extract user code between first try: and the nested try: that sets lastResult
          const codeLines: string[] = [];
          let inUser = false;
          for (let i = 0; i < b.lines.length; i++) {
            const l = b.lines[i];
            if (!inUser && /^\s*try\s*:\s*$/.test(l)) { inUser = true; continue; }
            if (inUser) {
              if (/^\s*try\s*:\s*$/.test(l)) break; // reached nested try
              // strip 4-space indent if present
              codeLines.push(l.replace(/^\s{4}/, ''));
            }
          }

          const newId = `node_imp_${Date.now()}_${Math.floor(Math.random()*10000)}`;
          idMap[expId] = newId;
          const nodeObj: any = { id: newId, x, y, label: label || newId, inputs: inputVars.slice(), outputs: [], inputTypes: inputVars.map(()=> 'Any'), outputTypes: [], code: codeLines.join('\n'), lastResult: null };
          if (color) {
            nodeObj.color = color;
            try { nodeObj.style = nodeObj.style || {}; nodeObj.style.color = color; } catch (e) {}
          }
          if (isOutputFlag) nodeObj.isOutput = true;
          if (isInitFlag) nodeObj.isInit = true;
          nodes.push(nodeObj);
          createdNodes.push({ expId, id: newId, node: nodeObj, inputSources, flags: { isInit: isInitFlag, isOutput: isOutputFlag, color } });
        }

        // second pass: create edges based on inputSources
        let edgeSeq = 1;
        for (const c of createdNodes) {
          const toId = c.id;
          const inputs = c.node.inputs || [];
          for (let i = 0; i < (c.inputSources || []).length; i++) {
            const srcExp = c.inputSources[i];
            if (!srcExp) continue;
            const srcNew = idMap[srcExp];
            if (!srcNew) continue;
            // ensure source has at least one output placeholder
            const srcNode = nodes.find(n => n.id === srcNew) as any;
            if (srcNode) {
              srcNode.outputs = srcNode.outputs || [];
              if (srcNode.outputs.length === 0) srcNode.outputs.push('out');
            }
            const edgeObj = { id: `edge_imp_${Date.now()}_${edgeSeq++}`, from: { nodeId: srcNew, portIndex: 0 }, to: { nodeId: toId, portIndex: i } };
            edges.push(edgeObj as any);
          }
        }

        rebuildNodeModules();
        try { logDebug('importPython: created nodes', createdNodes.map(c => ({ expId: c.expId, id: c.id, flags: c.flags }))); } catch (e) {}
        logDebug('importPython: created', createdNodes.length, 'nodes and', edges.length, 'edges');
      } catch (e) { logDebug('importPython error', e); }
    }

    function nodeCategoryColor(cat?: string) {
      const map: Record<string, string> = {
        inputs: '#6CA0FF',
        math: '#9B8CFF',
        outputs: '#6DD98D',
        knowledge: '#5B8FF9',
        components: '#F4C95D',
        programmable: '#7C6BFF',
        tools: '#3BA272',
        llm: '#8A63D2',
        const: '#FFB86B',
        text: '#FF8AB6',
        add: '#9B8CFF',
        mul: '#9B8CFF',
        'string-format': '#C970D9',
        'matrix-mul': '#6E9CF8',
        'list-map': '#5B8FF9',
        'dict-merge': '#4C9B8A',
        print: '#6DD98D',
        note: '#F4C95D',
        'file-read': '#4F8EF7',
        'file-write': '#3BA272',
        'url-parse': '#EEA33C',
        'http-request': '#D96C6C',
        'llm-chat': '#8A63D2',
        'agent-task': '#5B8FF9',
        'pdf-parse': '#F08A5D',
        'chunk-split': '#4C9B8A',
        'var-merge': '#5B8FF9',
        'api-embedding': '#8A63D2',
        'keyword-search': '#E6A23C',
        'index-search': '#D96C6C'
      };
      return cat ? map[cat] || '#9B9B9B' : '#9B9B9B';
    }

    function nodeStyle(node: Node): CSSProperties {
      if (node.category === 'note') {
        return {
          position: 'absolute',
          left: node.x + 'px',
          top: node.y + 'px',
          width: '220px',
          height: '160px'
        } as CSSProperties;
      }
      const rows = Math.max((node.inputs?.length || 0) + (node.outputs?.length || 0), 1);
      // include gaps between rows so content doesn't overflow the node container
      const h = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
      return {
        position: 'absolute',
        left: node.x + 'px',
        top: node.y + 'px',
        width: NODE_W + 'px',
        height: h + 'px'
      } as CSSProperties;
    }

    function isNodeDisabled(node: Node) {
      try {
        for (const f of folders) {
          if (f.children && f.children.indexOf(node.id) >= 0) {
            // if explicit map exists and entry is false -> disabled
            if (f._childEnabled && f._childEnabled[node.id] === false) return true;
          }
        }
      } catch (e) {}
      return false;
    }

    // recompute folder size to fit children with padding
    function updateFolderBounds(folder: any) {
      try {
        const pad = 18;
        const topPad = 44; // larger reserved space above children
        // If a node is being dragged and is very close to this folder's top edge (vertical distance),
        // skip resizing to avoid trapping the node when moving toward or out of the folder.
        try {
          const threshold = 44; // pixels (vertical)
          if ((dragging as any) && (dragging as any).node) {
            const dnode = (dragging as any).node as Node;
            if (Math.abs(dnode.y - (folder.y || 0)) <= threshold) {
              return;
            }
          }
        } catch (e) {}
        const minW = 160;
        const minH = 120;
        const members = (folder.children || []).map((id: string) => nodes.find(n => n.id === id)).filter(Boolean);
        if (members.length === 0) {
          // keep existing size if no members
          folder.w = folder.w || minW;
          folder.h = folder.h || minH;
          return;
        }
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const m of members) {
          minX = Math.min(minX, m.x);
          minY = Math.min(minY, m.y);
          const rows = Math.max((m.inputs?.length || 0) + (m.outputs?.length || 0), 1);
          const mh = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
          maxX = Math.max(maxX, m.x + NODE_W);
          maxY = Math.max(maxY, m.y + mh);
        }
        // desired bounds (with padding on all sides)
        const newLeft = Math.max(0, Math.floor(minX - pad));
        // leave extra space above children so node drag toward top isn't blocked
        const newTop = Math.max(0, Math.floor(minY - topPad));
        const newW = Math.max(minW, Math.ceil((maxX - minX) + pad * 2));
        const newH = Math.max(minH, Math.ceil((maxY - minY) + pad * 2 + (topPad - pad)));
        // apply computed bounds (allow shrinking and growing)
        folder.x = newLeft;
        folder.y = newTop;
        folder.w = newW;
        folder.h = newH;
      } catch (e) {}
    }

    // Fold a folder into a single representative node
    function foldFolder(folderId: string) {
      const folder = folders.find((f: any) => f.id === folderId);
      if (!folder || folder._folded) return;
      const memberIds = (folder.children || []).slice();
      if (memberIds.length === 0) return;

      // collect member nodes and edges involving them
      const memberNodes = nodes.filter(n => memberIds.includes(n.id));
      const memberNodeIds = new Set(memberNodes.map(n => n.id));
      const relatedEdges = edges.filter(e => memberNodeIds.has(e.from.nodeId) || memberNodeIds.has(e.to.nodeId));

      // determine interface ports
      const inputNodes = memberNodes.filter(n => (n as any).isInit);
      const outputNodes = memberNodes.filter(n => (n as any).isOutput);
      const inputs = inputNodes.map(n => n.label || n.id);
      const outputs = outputNodes.map(n => n.label || n.id);

      // create folded node
      const foldedId = `fold_${folder.id}_${Date.now()}`;
      const fx = folder.x || 0;
      const fy = folder.y || 0;
      const foldedNode: any = {
        id: foldedId,
        x: fx + 12,
        y: fy + 12,
        label: folder.label || 'Folded',
        inputs: inputs.slice(),
        outputs: outputs.slice(),
        inputTypes: inputs.map(()=> 'Any'),
        outputTypes: outputs.map(()=> 'Any'),
        code: '',
        lastResult: null,
        isInit: false,
        meta: {
          nodeKind: 'composite',
          description: '由文件夹中的节点流封装而成，可折叠或展开',
          composite: {
            folderId
          }
        }
      };

      // map external edges to folded node ports
      const newEdges: any[] = [];
      // for edges that come from external -> member (incoming to member), connect to foldedNode input port
      for (const e of relatedEdges) {
        // incoming external -> member
        if (!memberNodeIds.has(e.from.nodeId) && memberNodeIds.has(e.to.nodeId)) {
          // find which member node target is
          const tgtId = e.to.nodeId;
          // find index in inputNodes
          const idx = inputNodes.findIndex(n => n.id === tgtId);
          const portIndex = idx >= 0 ? idx : 0;
          newEdges.push({ id: `edge_fold_in_${Date.now()}_${Math.floor(Math.random()*10000)}`, from: { nodeId: e.from.nodeId, portIndex: e.from.portIndex }, to: { nodeId: foldedId, portIndex } });
        }
        // outgoing member -> external
        if (memberNodeIds.has(e.from.nodeId) && !memberNodeIds.has(e.to.nodeId)) {
          const srcId = e.from.nodeId;
          const idx = outputNodes.findIndex(n => n.id === srcId);
          const portIndex = idx >= 0 ? idx : 0;
          newEdges.push({ id: `edge_fold_out_${Date.now()}_${Math.floor(Math.random()*10000)}`, from: { nodeId: foldedId, portIndex: portIndex }, to: { nodeId: e.to.nodeId, portIndex: e.to.portIndex } });
        }
      }

      // backup and remove member nodes and related edges
      const backup = { nodes: memberNodes.map(n => JSON.parse(JSON.stringify(n))), edges: relatedEdges.map(e => JSON.parse(JSON.stringify(e))) };
      // remove edges
      for (const re of relatedEdges) {
        const idx = edges.findIndex(ed => ed.id === re.id);
        if (idx >= 0) edges.splice(idx, 1);
      }
      // remove nodes
      for (const mn of memberNodes) {
        const idx = nodes.findIndex(nn => nn.id === mn.id);
        if (idx >= 0) nodes.splice(idx, 1);
      }

      // add folded node and new edges
      nodes.push(foldedNode);
      for (const ne of newEdges) edges.push(ne);

      // preserve original children list and replace with folded node for display
      try { folder._origChildren = (folder.children || []).slice(); } catch (e) {}
      folder.children = [foldedId];
      folder._folded = true;
      folder._backup = backup;
      folder._foldedNodeId = foldedId;

      rebuildNodeModules();
      logDebug('foldFolder:', folderId, '->', foldedId, 'inputs', inputs, 'outputs', outputs, 'createdEdges', newEdges.length);
    }

    function unfoldFolder(folderId: string) {
      const folder = folders.find((f: any) => f.id === folderId);
      if (!folder || !folder._folded) return;
      const foldedId = folder._foldedNodeId;
      // remove folded node
      const fIdx = nodes.findIndex(n => n.id === foldedId);
      if (fIdx >= 0) nodes.splice(fIdx, 1);
      // remove edges connected to folded node
      for (let i = edges.length - 1; i >= 0; i--) {
        const e = edges[i];
        if (e.from.nodeId === foldedId || e.to.nodeId === foldedId) edges.splice(i, 1);
      }

      // restore backup nodes and edges
      try {
        const backup = folder._backup;
        if (backup && backup.nodes) {
          for (const n of backup.nodes) nodes.push(n);
        }
        if (backup && backup.edges) {
          for (const e of backup.edges) edges.push(e);
        }
      } catch (e) { logDebug('unfoldFolder restore error', e); }

      // restore original children list
      try { folder.children = folder._origChildren || folder.children || []; } catch (e) {}
      // cleanup folder flags
      folder._folded = false;
      folder._backup = undefined;
      folder._foldedNodeId = undefined;
      folder._origChildren = undefined;

      rebuildNodeModules();
      logDebug('unfoldFolder:', folderId, 'restored');
    }

    function onNodePointerDown(e: PointerEvent, node: Node) {
      return interactions.handleNodePointerDown(e, node);
    }

    function onNodePointerEnter(e: PointerEvent, node: Node) {
      nodeHoverPreview.value = {
        visible: true,
        x: e.clientX + 16,
        y: e.clientY + 16,
        node
      };
    }

    function onNodePointerMove(e: PointerEvent, node: Node) {
      if (!nodeHoverPreview.value.visible) return;
      nodeHoverPreview.value = {
        visible: true,
        x: e.clientX + 16,
        y: e.clientY + 16,
        node
      };
    }

    function onNodePointerLeave() {
      nodeHoverPreview.value.visible = false;
    }

    function onPointerMoveWindow(e: PointerEvent) {
      return interactions.handlePointerMoveWindow(e);
    }

    // temp edge path now provided by interactions composable
    function tempEdgePath() {
      return interactions.getTempEdgePath();
    }



    function onPointerUpWindow(e: PointerEvent) {
      return interactions.handlePointerUpWindow(e);
    }

    function startEdge(ev: PointerEvent, node: Node, type: 'in' | 'out', portIndex: number) {
      return interactions.handleStartEdge(ev, node, type, portIndex);
    }



    function portColor(node: Node, side: 'in' | 'out') {
      // color ports by node category with slight variant for direction
      const base = nodeCategoryColor(node.category);
      // make a subtle variant for inputs (darker) vs outputs (lighter)
      if (side === 'in') return adjustAlpha(base, 0.95);
      return adjustAlpha(base, 0.8);
    }

    function adjustAlpha(hex: string, alpha: number) {
      // hex like #RRGGBB
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function onPointerDownArea(e: PointerEvent) {
      return interactions.handlePointerDownArea(e);
    }


    function addPresetFromPanel(item: { key: string; label: string; desc?: string }) {
      const area = areaRef.value!;
      const rect = area.getBoundingClientRect();
      // place near top-left of editor with a larger inset margin
      const margin = 48;
      const baseX = margin + (nodes.length % 6) * 18;
      const baseY = margin + Math.floor(nodes.length / 6) * 18;
      const x = clamp(baseX, margin, Math.max(margin, rect.width - NODE_W - margin));
      const defaultH = headerHeight + BODY_PADDING * 2 + rowHeight;
      const y = clamp(baseY, margin, Math.max(margin, rect.height - defaultH - margin));
      createNodeByPreset(item, x, y);
    }

    // wheel zoom: handled by interactions composable
    function onWheel(e: WheelEvent) {
      return interactions.handleWheel(e);
    }

    // helper to check if a node is selected
    function isNodeSelected(id: string) {
      return selectedIds.value.includes(id);
    }

    function updateNodeLabel(id: string, label: string) {
      const n = nodes.find(x => x.id === id);
      if (n) n.label = label;
    }

    // Template event handlers that safely access event.target.value with proper casting
    function handleNodeLabelInput(e: Event) {
      const v = (e.target as HTMLInputElement)?.value;
      if (!v) return;
      const id = selectedNode?.value ? selectedNode.value.id : null;
      if (id) updateNodeLabel(id, v);
    }

    function handleNodeIOInput(id: string, side: 'in' | 'out', idx: number, e: Event) {
      const v = (e.target as HTMLInputElement)?.value;
      updateNodeIO(id, side, idx, v || '');
    }

    function handleNodeInputTypeInput(id: string, idx: number, e: Event) {
      const v = (e.target as HTMLInputElement)?.value;
      updateNodeInputType(id, idx, v || '');
    }

    function handleNodeOutputTypeInput(id: string, idx: number, e: Event) {
      const v = (e.target as HTMLInputElement)?.value;
      updateNodeOutputType(id, idx, v || '');
    }

    function addNodeIO(id: string, side: 'in' | 'out') {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      if (side === 'in') {
        n.inputs = n.inputs || [];
        n.inputs.push('');
        (n as any).inputTypes = (n as any).inputTypes || [];
        (n as any).inputTypes.push('Any');
      } else {
        n.outputs = n.outputs || [];
        // if code has functions with return and outputs is empty, prefill with 'return' or function name
        try {
          const md = modulesData[id] as any;
          if ((!n.outputs || n.outputs.length === 0) && md && md.functions && md.functions.length) {
            const fn = md.functions[0];
            if (fn.hasReturn) {
              n.outputs.push('return');
            } else {
              n.outputs.push('');
            }
          } else {
            n.outputs.push('');
          }
        } catch (e) {
          n.outputs.push('');
        }
        (n as any).outputTypes = (n as any).outputTypes || [];
        (n as any).outputTypes.push('Any');
      }
    }

    function removeNodeIO(id: string, side: 'in' | 'out', idx: number) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      if (side === 'in' && n.inputs) { n.inputs.splice(idx, 1); (n as any).inputTypes && (n as any).inputTypes.splice(idx,1); }
      if (side === 'out' && n.outputs) { n.outputs.splice(idx, 1); (n as any).outputTypes && (n as any).outputTypes.splice(idx,1); }
    }

    function updateNodeIO(id: string, side: 'in' | 'out', idx: number, val: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      if (side === 'in' && n.inputs) n.inputs[idx] = val;
      if (side === 'out' && n.outputs) n.outputs[idx] = val;
    }

    function handleUpdateFolderLabel(payload: { id: string; label: string }) {
      try {
        const f = folders.find(x => x.id === payload.id);
        if (!f) return;
        f.label = payload.label;
      } catch (e) {}
    }

    function handleUpdateFolderComment(payload: { id: string; comment: string }) {
      try {
        const f = folders.find(x => x.id === payload.id);
        if (!f) return;
        f.comment = payload.comment;
      } catch (e) {}
    }

    function handleToggleFolderChild(payload: { folderId: string; childId: string; enabled: boolean }) {
      try {
        const f = folders.find(x => x.id === payload.folderId);
        if (!f) return;
        f._childEnabled = f._childEnabled || {};
        f._childEnabled[payload.childId] = !!payload.enabled;
      } catch (e) {}
    }

    function handleUpdateProjectConfig(payload: { field: 'name' | 'description' | 'requires'; value: string }) {
      if (payload.field === 'name') moduleMeta.name = payload.value;
      if (payload.field === 'description') moduleMeta.description = payload.value;
      if (payload.field === 'requires') moduleMeta.requires = payload.value;
    }

    function addEnvVar() {
      envVars.push({ key: '', value: '', secret: false });
    }

    function removeEnvVar(index: number) {
      envVars.splice(index, 1);
    }

    function updateEnvVar(payload: { index: number; field: 'key' | 'value' | 'secret'; value: string | boolean }) {
      const env = envVars[payload.index];
      if (!env) return;
      if (payload.field === 'secret') env.secret = Boolean(payload.value);
      else (env as any)[payload.field] = String(payload.value);
    }

    function folderAllEnabled(f: any) {
      try {
        if (!f) return true;
        const children = f.children || [];
        if (children.length === 0) return false;
        if (!f._childEnabled) return true;
        return children.every((cid: string) => f._childEnabled[cid] !== false);
      } catch (e) { return true }
    }

    function toggleFolderChildren(f: any, enabled: boolean) {
      try {
        f._childEnabled = f._childEnabled || {};
        (f.children || []).forEach((cid: string) => {
          f._childEnabled[cid] = !!enabled;
        });
      } catch (e) {}
    }

    function updateNodeInputType(id: string, idx: number, val: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).inputTypes = (n as any).inputTypes || [];
      (n as any).inputTypes[idx] = val;
    }

    function updateNodeOutputType(id: string, idx: number, val: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).outputTypes = (n as any).outputTypes || [];
      (n as any).outputTypes[idx] = val;
    }

    function updateNodeMetaConfig(id: string, configText: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).meta = (n as any).meta || {};
      try {
        (n as any).meta.config = JSON.parse(configText || '{}');
      } catch (e) {
        logDebug('updateNodeMetaConfig parse error', e?.toString ? e.toString() : e);
      }
    }

    function attachNodeFiles(id: string, files: File[]) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      n.resources = n.resources || [];
      const next = files
        .filter(file => file instanceof File)
        .map(file => ({
          id: `${Date.now()}_${file.name}_${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          kind: file.type || 'application/pdf',
          file,
          size: file.size,
          lastModified: file.lastModified
        }));
      n.resources.push(...next);
    }

    function clearNodeFiles(id: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      n.resources = [];
    }

    function updateNodeNote(id: string, note: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).meta = (n as any).meta || {};
      (n as any).meta.note = note;
    }

    function updateNodeCode(id: string, code: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).code = code;
      rebuildNodeModules();
      // If functions detected in code, auto-bind first function's params -> inputs and return -> outputs
      try {
        const md = modulesData[id] as any;
        if (md && md.functions && md.functions.length) {
          const fn = md.functions[0];
          // set inputs to function params
          n.inputs = fn.params.length ? [...fn.params] : [];
          (n as any).inputTypes = (n as any).inputTypes || [];
          (n as any).inputTypes = n.inputs.map((p: string, i: number) => (n as any).inputTypes[i] || 'Any');
          // set outputs if function has return
          if (fn.hasReturn) {
            n.outputs = n.outputs && n.outputs.length ? n.outputs : ['return'];
            (n as any).outputTypes = (n as any).outputTypes || [];
            (n as any).outputTypes = n.outputs.map((o: string, i: number) => (n as any).outputTypes[i] || 'Any');
          }
        }
      } catch (e) { /* ignore parsing errors */ }
    }

    function updateNodeIsInit(id: string, isInit: boolean) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).isInit = !!isInit;
    }

    function updateNodeIsOutput(id: string, isOutput: boolean) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).isOutput = !!isOutput;
    }

    function handleUpdateIsOutput(isOutput: boolean) {
      const id = selectedNode?.value ? selectedNode.value.id : null;
      if (!id) { logDebug('handleUpdateIsOutput: no node selected'); return; }
      updateNodeIsOutput(id, isOutput);
    }

    function handleUpdateNodeColor(color: string) {
      const id = selectedNode?.value ? selectedNode.value.id : null;
      if (!id) { logDebug('handleUpdateNodeColor: no node selected'); return; }
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      (n as any).color = color;
      try { (n as any).style = (n as any).style || {}; (n as any).style.color = color; } catch (e) {}
    }

    function getNodePreviewText(node: Node | null) {
      if (!node) return '';
      const preset = getNodePreset(node.category);
      return (node as any).meta?.description || preset?.desc || '节点预览';
    }

    function nodeTopStyle(node: Node) {
      try {
        if (node.category === 'note') {
          return { background: 'linear-gradient(90deg, rgba(244,201,93,0.98), rgba(251,191,36,0.98))' } as CSSProperties;
        }
      } catch (e) {}
      try {
        if ((node as any).isOutput) {
          return { background: 'linear-gradient(90deg, rgba(255,90,90,0.98), rgba(220,60,60,0.98))' } as CSSProperties;
        }
      } catch (e) {}
      try {
        if ((node as any).isInit) {
          return { background: 'linear-gradient(90deg, rgba(94,170,255,0.95), rgba(75,140,255,0.95))' } as CSSProperties;
        }
      } catch (e) {}
      try {
        const col = (node as any).color;
        if (col) return { background: col } as CSSProperties;
      } catch (e) {}
      return { background: nodeCategoryColor(node.category) } as CSSProperties;
    }

    function folderStatus(folder: any) {
      try {
        // determine member nodes: prefer backup nodes when folded, else folder.children
        let members: any[] = [];
        if (folder._folded) {
          if (folder._backup && folder._backup.nodes) members = folder._backup.nodes;
          else if (folder._origChildren) members = nodes.filter(n => (folder._origChildren || []).includes(n.id));
        } else {
          members = nodes.filter(n => (folder.children || []).includes(n.id));
        }
        if (!members || members.length === 0) return 'idle';
        const counts: Record<string, number> = { error: 0, running: 0, done: 0, disabled: 0, idle: 0 };
        for (const m of members) {
          const s = (m as any).status || 'idle';
          counts[s] = (counts[s] || 0) + 1;
        }
        if (counts.error > 0) return 'error';
        if (counts.running > 0) return 'running';
        if (counts.disabled > 0) return 'disabled';
        if (counts.done > 0 && counts.done === members.length) return 'done';
        return 'idle';
      } catch (e) { return 'idle'; }
    }

    function insertTemplate(id: string) {
      const n = nodes.find(x => x.id === id);
      if (!n) return;
      if (isBuiltinNode(n.category)) return;
      const inputsArr: string[] = n.inputs || [];
      const typesArr: string[] = (n as any).inputTypes || [];
      const outputsArr: string[] = n.outputs || [];
      const paramsComment = inputsArr.map((name, i) => `# ${name || 'arg'+i}: ${(typesArr[i] || 'Any')}`).join('\n');
      const retDesc = outputsArr.length === 0 ? '# returns: None' : `# returns: ${outputsArr.join(', ')}`;
      const exampleReturn = outputsArr.length === 1 ? `res = ${outputsArr[0]}` : (outputsArr.length > 1 ? `res = { ${outputsArr.map(o=>`'${o}': None`).join(', ')} }` : 'res = None');
      const tpl = `# Parameters:\n${paramsComment}\n${retDesc}\n\n# Write your code below, assign the output to variable \`res\`\n\n${exampleReturn}`;
      (n as any).code = tpl;
    }



    onBeforeUnmount(() => {
      window.removeEventListener('pointermove', onPointerMoveWindow);
      window.removeEventListener('pointerup', onPointerUpWindow);
    });
    </script>

<template>
  <div class="page-blank" style="padding:12px;display:flex;flex-direction:column;height:100%">
    <div class="editor-layout" style="flex:1;display:flex;gap:8px;height:100%">
      <LeftSidebar
        :categories="categories"
        :left-collapsed="leftCollapsed"
        :node-category-color="nodeCategoryColor"
        :project-config="projectConfig"
        :env-vars="envVars"
        :saved-node-templates="savedNodeTemplates"
        :workflow-templates="WORKFLOW_TEMPLATES"
        :workflow-template-groups="WORKFLOW_TEMPLATE_GROUPS"
        :cloud-module-count="cloudModuleCount"
        @toggle="leftCollapsed = !leftCollapsed"
        @add-preset="addPresetFromPanel"
        @apply-workflow-template="applyWorkflowTemplate"
        @update-project-config="handleUpdateProjectConfig"
        @add-env-var="addEnvVar"
        @remove-env-var="removeEnvVar"
        @update-env-var="updateEnvVar"
        @import-saved-template="importSavedTemplate"
        @delete-saved-template="deleteSavedTemplate"
        @save-personal-module="saveWorkspaceToPersonalModule"
      />

      <div ref="areaRef" class="editor-area" style="flex:1;position:relative;border-radius:6px;overflow:visible" @pointerdown="onPointerDownArea">
        <!-- Editor toolbar positioned inside workspace -->
        <EditorToolbar
          :pan-mode="panMode"
          :exec-status="execStatus"
          :project-name="projectConfig.name"
          :left-offset="toolbarLeftOffset"
          :right-offset="toolbarRightOffset"
          @add="addNode"
          @run-graph="executeGraph"
          @clear="clearAll"
          @export="exportModel"
          @export-py="exportPython"
          @import-py="openFileDialog"
          @import-node="openNodeTemplateDialog"
          @toggle-pan="panMode = !panMode"
        />
        <!-- ear buttons: visible when corresponding sidebar is collapsed -->
        <button v-if="leftCollapsed" class="sidebar-ear left" @click.stop="leftCollapsed = false">></button>
        <button v-if="rightCollapsed" class="sidebar-ear right" @click.stop="rightCollapsed = false"><</button>
        <div class="viewport" :style="viewportStyle" @wheel.prevent="onWheel">
          <!-- folders (render under nodes) -->
          <div v-for="f in folders" :key="f.id" class="folder" :class="{ 'folder-hover': f._hover, selected: selectedIds.includes(f.id) }" :style="{ left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: f.h + 'px' }" @pointerdown="(e) => onFolderPointerDown(e, f)">
            <div class="folder-top" @pointerdown="(e) => onFolderPointerDown(e, f)">
              <div class="folder-toggle" @pointerdown.stop @click.stop>
                <input type="checkbox" class="folder-switch" :checked="folderAllEnabled(f)" @change="(e) => toggleFolderChildren(f, (e.target as HTMLInputElement).checked)" />
              </div>
              <div class="folder-label">{{ f.label || 'Folder' }}</div>
              <div class="folder-count">{{ (f.children && f.children.length) || 0 }}</div>
              <div style="margin-left:8px; display:flex; gap:6px; align-items:center">
                <div class="folder-indicator" :class="folderStatus(f)" :title="folderStatus(f)"></div>
                <button class="btn-mini" title="折叠/展开" @click.stop.prevent="(e) => { if (f._folded) unfoldFolder(f.id); else foldFolder(f.id); }">{{ f._folded ? '展开' : '折叠' }}</button>
              </div>
            </div>
          </div>
          <div
            v-for="node in nodes"
            :key="node.id"
            class="node"
            :class="{ selected: selectedIds.includes(node.id), 'child-disabled': isNodeDisabled(node) }"
            :style="nodeStyle(node)"
            @pointerdown="onNodePointerDown($event, node)"
            @pointerenter="onNodePointerEnter($event, node)"
            @pointermove="onNodePointerMove($event, node)"
            @pointerleave="onNodePointerLeave"
          >
            <div class="node-top" :style="nodeTopStyle(node)">
              <div style="display:flex;align-items:center;gap:8px;width:100%">
                <div class="node-header">{{ node.label }}</div>
                <div style="margin-left:auto; display:flex; align-items:center">
                  <div class="node-indicator" :class="node.status || 'idle'" :title="node.status || 'idle'"></div>
                </div>
              </div>
            </div>
            <div class="node-body">
              <template v-if="node.category === 'note'">
                <div class="note-body">{{ node.meta?.note || '右侧属性面板中编辑便签内容' }}</div>
              </template>
              <template v-else>
              <div v-for="(input, idx) in node.inputs || []" :key="node.id + '-in-' + idx" class="node-row">
                <div class="port-wrap left"><div class="port in" :style="{ background: portColor(node, 'in') }" :class="{ 'port-hover': hoverPort && hoverPort.nodeId === node.id && hoverPort.type === 'in' && hoverPort.index === idx, 'port-invalid': hoverPort && hoverPort.invalid && hoverPort.nodeId === node.id && hoverPort.type === 'in' && hoverPort.index === idx }" @pointerdown.stop.prevent="startEdge($event, node, 'in', idx)"></div></div>
                <div class="field-label">{{ input }}</div>
              </div>
              <div v-for="(output, idx) in node.outputs || []" :key="node.id + '-out-' + idx" class="node-row">
                <div class="field-label">{{ output }}</div>
                <div class="port-wrap right"><div class="port out" :style="{ background: portColor(node, 'out') }" :class="{ 'port-hover': hoverPort && hoverPort.nodeId === node.id && hoverPort.type === 'out' && hoverPort.index === idx }" @pointerdown.stop.prevent="startEdge($event, node, 'out', idx)"></div></div>
              </div>
              </template>
            </div>
          </div>

          <!-- Context menu: vertical categorized list (rendered at editor root so it's not nested in nodes) -->
          <Teleport to="body">
            <div v-if="contextMenu.visible" class="ctx-menu-vertical" :style="{ left: contextMenu.pageX + 'px', top: contextMenu.pageY + 'px', position: 'fixed' }" @click.stop>
              <div class="ctx-categories">
                <div v-for="(cat, cidx) in categories" :key="cat.key" class="ctx-cat" @mouseenter="onHoverCategory(cat.key, $event)" @mouseleave="onLeaveCategory">
                  <div class="ctx-cat-label">{{ cat.label }}</div>
                </div>
              </div>
              <!-- submenu: appears on hover over a category -->
              <Transition name="submenu-fade">
                <div v-if="submenu.visible" class="ctx-submenu" :style="{ left: submenu.x + 'px', top: submenu.y + 'px' }" @mouseenter="cancelHideSubmenu" @mouseleave="scheduleHideSubmenu">
                  <div v-for="it in submenu.items" :key="it.key" class="ctx-subitem" @click="addPresetNode(it)">
                    <div class="ctx-item-title">{{ it.label }}</div>
                    <div class="ctx-item-desc">{{ it.desc }}</div>
                  </div>
                </div>
              </Transition>
            </div>
          </Teleport>
          <Teleport to="body">
            <div v-if="nodeHoverPreview.visible && nodeHoverPreview.node" class="node-hover-preview" :style="{ left: nodeHoverPreview.x + 'px', top: nodeHoverPreview.y + 'px' }">
              <div class="node-hover-head" :style="{ background: nodeTopStyle(nodeHoverPreview.node).background as string }">
                {{ nodeHoverPreview.node.label }}
              </div>
              <div class="node-hover-body">
                <div class="node-hover-kind">{{ nodeHoverPreview.node.meta?.nodeKind || nodeHoverPreview.node.category || 'node' }}</div>
                <div class="node-hover-desc">{{ getNodePreviewText(nodeHoverPreview.node) }}</div>
                <div class="node-hover-ports">
                  <span>In {{ (nodeHoverPreview.node.inputs || []).length }}</span>
                  <span>Out {{ (nodeHoverPreview.node.outputs || []).length }}</span>
                </div>
              </div>
            </div>
          </Teleport>

          <svg class="edge-layer" width="100%" height="100%" overflow="visible" style="position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1100">
            <!-- debug test line removed -->
            <!-- Bezier curve for persisted edges -->
            <path v-for="edge in edges" :key="edge.id" :d="edgePath(edge, nodes)" stroke="#3D7CFF" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
            <!-- Bezier preview while dragging -->
            <path v-if="tempEdge" :d="tempEdgePath()" :stroke="(hoverPort && hoverPort.invalid) ? '#FF4D4F' : '#3D7CFF'" stroke-width="3" stroke-dasharray="6 4" fill="none" stroke-linecap="round" />
            <circle v-if="tempEdge" :cx="tempEdge.x1" :cy="tempEdge.y1" r="4" :fill="(hoverPort && hoverPort.invalid) ? '#FF4D4F' : '#3D7CFF'" />
            <circle v-if="tempEdge" :cx="tempEdge.x2" :cy="tempEdge.y2" r="5" :fill="(hoverPort && hoverPort.invalid) ? '#FF4D4F' : '#3D7CFF'" />
          </svg>
          <!-- hidden file input for importing python files -->
          <input ref="fileInputRef" style="display:none" type="file" accept=".py" @change="(e) => handleImportFile(e)" />
          <input ref="nodeTemplateInputRef" style="display:none" type="file" accept=".json" @change="(e) => handleImportNodeTemplateFile(e)" />
          <!-- update folder bounds reactively when nodes change -->
          <div style="display:none">
            <div v-for="f in folders" :key="f.id">{{ updateFolderBounds(f) }}</div>
          </div>
          <!-- marquee selection rectangle (in world coordinates) -->
          <div v-if="marquee.visible" class="marquee" :style="{ left: marquee.x + 'px', top: marquee.y + 'px', width: marquee.w + 'px', height: marquee.h + 'px' }"></div>
        </div>

        <DebugPanel :show="showDebug" :py-ready="pyReady" :py-code="pyCode" :py-packages="pyPackages" :logs="debugLogs" @run-py="handleDebugRun" @install="handleDebugInstall" />
      </div>

      <RightSidebar
        :selected-node="selectedNode" :selected-folder="selectedFolder" :nodes="nodes" :right-collapsed="rightCollapsed"
        @toggle="rightCollapsed = !rightCollapsed"
        @update-label="handleNodeLabelInput"
        @update-i-o="onUpdateIO"
        @update-input-type="onUpdateInputType"
        @update-output-type="onUpdateOutputType"
        @add-i-o="onAddIO"
        @remove-i-o="onRemoveIO"
        @insert-template="handleInsertTemplate"
        @run-node="handleRunSelectedNode"
        @save-code="handleSaveCode"
        @update-is-init="handleUpdateIsInit"
        @update-is-output="handleUpdateIsOutput"
        @update-node-color="handleUpdateNodeColor"
        @update-node-meta-config="handleUpdateNodeMetaConfig"
        @attach-node-files="handleAttachNodeFiles"
        @clear-node-files="handleClearNodeFiles"
        @save-node-template="saveSelectedNodeTemplate"
        @upload-node-template="uploadSelectedNodeTemplate"
        @update-node-note="handleUpdateNodeNote"
        @update-folder-label="handleUpdateFolderLabel"
        @update-folder-comment="handleUpdateFolderComment"
        @toggle-folder-child="handleToggleFolderChild"
      />

      <BottomPanel
        :bottom-collapsed="bottomCollapsed"
        :module-paths="modulePaths"
        :modules-data="modulesData"
        :selected-module="selectedModule"
        :left-collapsed="leftCollapsed"
        :right-collapsed="rightCollapsed"
        :logs="debugLogs"
        :env-vars="envVars"
        :watch-items="watchItems"
        @toggle="bottomCollapsed = !bottomCollapsed"
        @load="loadModule"
        @scroll="scrollToExport"
        @save-module="handleSaveModule"
      />
      <NButton class="suggestion-trigger" secondary @click="suggestionModalVisible = true">修改建议</NButton>
      <NModal v-model:show="suggestionModalVisible" preset="card" title="模块修改建议" style="width: 560px">
        <div class="suggestion-list">
          <div v-for="(item, index) in workspaceSuggestions" :key="index" class="suggestion-item" :class="item.level">
            <div class="suggestion-title">{{ item.title }}</div>
            <div class="suggestion-detail">{{ item.detail }}</div>
          </div>
        </div>
      </NModal>
    </div>
  </div>
</template>

    <style>
    .__debug-panel { position: fixed; left: 12px; bottom: 12px; width:320px; max-height:40vh; background: rgba(20,20,20,0.85); color: #e6eef9; font-size:12px; border-radius:8px; overflow:hidden; z-index:99999; box-shadow:0 8px 30px rgba(0,0,0,0.4); }
    .__debug-header { padding:6px 8px; border-bottom:1px solid rgba(255,255,255,0.04); font-weight:700 }
    .__debug-body { padding:6px 8px; overflow:auto; max-height:calc(40vh - 36px) }
    .__debug-line { padding:2px 0; white-space:pre-wrap; word-break:break-word; opacity:0.9 }

    .editor-area { background: var(--n-foreground-3); background-image: radial-gradient(circle, rgba(82, 82, 82, 0.272) 1px, transparent 1px); background-size: 12px 12px; }
    .viewport { position:absolute; left:0; top:0; width:100%; height:100%; transform-origin:0 0 }
    .editor-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; padding:8px 12px; border-radius:8px; background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.02)); box-shadow: 0 4px 20px rgba(0,0,0,0.04); }
    .editor-toolbar .toolbar-left { display:flex; gap:8px; align-items:center }
    .editor-toolbar .toolbar-right { display:flex; gap:8px; align-items:center }
    .editor-toolbar .toolbar-hint { color:var(--n-text-2); font-size:13px; padding-left:8px }
    .editor-toolbar n-button { --n-button-border-radius: 6px }
    .node { background-color: var(--n-card); background-clip: padding-box; border-radius:6px; box-shadow:0 2px 6px rgba(0,0,0,0.08); cursor:grab; user-select:none; border:1px solid rgba(0,0,0,0.06); display:flex; flex-direction:column; overflow:hidden }
    .node:active { cursor:grabbing }
    .node-top { height:32px; border-top-left-radius:6px; border-top-right-radius:6px; display:flex; align-items:center; padding:0 10px }
    .node-header { font-weight:600; color:white }
    .node-body { padding:8px; display:flex; flex-direction:column; gap:6px }
    .node-row { display:flex; align-items:center; gap:8px; height:28px }
    .field-label { flex:1; color:var(--n-text-1) }
    .note-body { white-space: pre-wrap; word-break: break-word; color: var(--n-text-1); line-height: 1.45; font-size: 13px; }
    .port-wrap { width:24px; display:flex; align-items:center; justify-content:center }
    .port { width:12px; height:12px; border-radius:50%; background:var(--n-foreground-1); box-shadow:0 1px 2px rgba(0,0,0,0.12) }
    .port.in { box-shadow:0 1px 2px rgba(0,0,0,0.12); border:1px solid rgba(0,0,0,0.06); }
    .port.out { box-shadow:0 1px 2px rgba(0,0,0,0.12); border:1px solid rgba(0,0,0,0.06); }
    .port { transition: transform 120ms ease, box-shadow 120ms ease }
    .port:hover { transform:scale(1.15); box-shadow:0 4px 10px rgba(0,0,0,0.12) }
    .port-hover { outline: 2px solid rgba(83,135,255,0.9); transform:scale(1.2); }
    .port-invalid { outline: 2px solid rgba(255,77,79,0.95); transform:scale(1.2); }
    .port-wrap.left { padding-left:6px }
    .port-wrap.right { padding-right:6px }
    .edge-layer { z-index:1100; overflow: visible }
    .node { z-index:1001 }
    .folder { position:absolute; background:rgba(240,246,255,0.45); border:1px dashed rgba(60,120,220,0.35); border-radius:8px; padding:8px; z-index:100; box-sizing:border-box; transition:transform .12s ease, box-shadow .12s ease, border-color .12s ease }
    .folder-top { display:flex; align-items:center; justify-content:space-between; gap:8px; cursor:grab; padding:6px; border-bottom:1px solid rgba(0,0,0,0.04); border-radius:6px }
    .folder-toggle { display:flex; align-items:center; margin-right:8px }
    .folder-switch { width:16px; height:16px; cursor:pointer }
    .folder-label { font-weight:700; color:var(--n-text-2); font-size:13px }
    .folder-count { background:rgba(0,0,0,0.06); color:var(--n-text-2); padding:4px 8px; border-radius:12px; font-size:12px }
    .folder-hover { transform:scale(1.02); box-shadow:0 12px 36px rgba(60,120,220,0.12); border-color:rgba(60,120,220,0.9) }
    .folder.selected { box-shadow: 0 0 0 6px rgba(83,135,255,0.12), 0 12px 36px rgba(83,135,255,0.06); border-color: rgba(83,135,255,0.9) }
    .node.selected { box-shadow: 0 0 0 4px rgba(83,135,255,0.12), 0 10px 30px rgba(83,135,255,0.06); border:1px solid rgba(83,135,255,0.2) }

    .editor-layout { position:relative; display:flex; height:100% }
    /* allow theme to override panel backgrounds via CSS variables */
    .page-blank { --editor-sidebar-bg: rgba(255,255,255,0.06); --editor-ctx-bg: rgba(20, 20, 20, 0.524); height:100vh; overflow:hidden }
    .sidebar { width:280px; background-color: var(--editor-sidebar-bg); border-radius:8px; padding:10px; box-shadow:0 12px 40px rgba(2,6,23,0.12); display:flex; flex-direction:column; transition: width 420ms cubic-bezier(.22,1,.36,1), transform 420ms cubic-bezier(.22,1,.36,1), box-shadow 420ms cubic-bezier(.22,1,.36,1), opacity 220ms ease; position:absolute; top:8px; bottom:8px; z-index:2500; overflow:hidden; will-change: width, transform }
    .sidebar.left { left:8px; transform:translateX(0) }
    .sidebar.right { right:8px; transform:translateX(0) }
    /* collapsed: shrink to a narrow bar so the toggle remains visible */
    .sidebar.left.collapsed { width:48px; transform: translateX(-6px); opacity:1; box-shadow:0 6px 20px rgba(2,6,23,0.06) }
    .sidebar.right.collapsed { width:48px; transform: translateX(6px); opacity:1; box-shadow:0 6px 20px rgba(2,6,23,0.06) }
    .sidebar-toggle { cursor:pointer; padding:6px; text-align:center; font-weight:700; border-radius:6px; background:rgba(0,0,0,0.04); width:36px; height:36px; display:flex; align-items:center; justify-content:center; position:absolute; top:12px; box-shadow:0 6px 18px rgba(0,0,0,0.06) }
    .sidebar.left .sidebar-toggle { left:-18px }
    .sidebar.right .sidebar-toggle { right:-18px }
    .sidebar:not(.collapsed) .sidebar-toggle { background:transparent; box-shadow:none }
    .sidebar-content { overflow:auto; padding-right:6px }
    .sidebar-content.collapsed { display:none }
    .sidebar-title { font-weight:700; padding:6px 4px; border-bottom:1px solid rgba(0,0,0,0.04); margin-bottom:8px }
    .preset-grid { padding-bottom:12px }
    .preset-items { max-height: calc(100vh - 220px); overflow:auto }
    .sidebar-title { font-weight:700; padding:6px 4px }
    .preset-grid { overflow:auto }
    .preset-section { margin-bottom:8px }
    .preset-section-title { font-weight:600; padding:6px 0 }
    .preset-items { display:flex; gap:8px; flex-wrap:wrap }
    .preset-item { display:flex; align-items:center; gap:8px; padding:6px; cursor:pointer; border-radius:6px }
    .preset-icon { width:28px; height:28px; border-radius:6px }
    .preset-label { font-size:13px }

    .prop-row { display:flex; align-items:center; gap:8px; padding:6px 0 }
    .prop-val { color:var(--n-text-1) }
    .prop-input { width:100%; padding:6px; border-radius:6px; border:1px solid rgba(0,0,0,0.06); background:transparent }
    .prop-section { margin-top:8px; padding-top:6px; border-top:1px dashed rgba(0,0,0,0.04) }
    .prop-section-title { font-weight:600; margin-bottom:6px }
    .prop-item { display:flex; gap:8px; align-items:center; margin-bottom:6px }
    .btn-sm { padding:6px 8px; border-radius:6px; cursor:pointer; background:rgba(0,0,0,0.04); border:1px solid rgba(0,0,0,0.04) }
    .btn-mini { padding:4px 6px; border-radius:4px; cursor:pointer }
    .no-selection { color:var(--n-text-2); padding:8px }
    .sidebar-ear { position:absolute; top:72px; z-index:1600; width:34px; height:34px; border-radius:8px; background:var(--n-card); box-shadow:0 6px 18px rgba(0,0,0,0.08); display:flex; align-items:center; justify-content:center; cursor:pointer; transition: transform 320ms cubic-bezier(.22,1,.36,1), opacity 220ms ease }
    .sidebar-ear.left { left:10px }
    .sidebar-ear.right { right:10px }
    .sidebar-ear:hover { transform:scale(1.03) }
    .marquee { position:absolute; border:1px dashed rgba(61,124,255,0.9); background:rgba(61,124,255,0.06); pointer-events:none; z-index:1500 }
    .ctx-menu-vertical { position:absolute; min-width:220px; max-width:420px; max-height:480px; display:flex; flex-direction:row; gap:8px; background-color: var(--n-card); background-clip: padding-box; box-shadow:0 18px 48px rgba(2,6,23,0.2); border-radius:10px; padding:8px; overflow:visible; z-index:3200; border:1px solid rgba(0,0,0,0.08); pointer-events:auto }
    .ctx-categories { min-width:220px; display:flex; flex-direction:column; gap:6px; }
    .ctx-cat { padding:8px 12px; border-radius:8px; cursor:default }
    .ctx-cat:hover { background: rgba(0,0,0,0.04) }
    .ctx-cat-label { font-weight:700 }
    .ctx-submenu { position:fixed; min-width:240px; max-height:420px; overflow:auto; background:var(--n-card); box-shadow:0 18px 48px rgba(2,6,23,0.18); border-radius:8px; border:1px solid rgba(0,0,0,0.06); padding:8px; z-index:3300 }
    .ctx-subitem { padding:8px 10px; border-radius:6px; cursor:pointer }
    .ctx-subitem:hover { background:rgba(0,0,0,0.04) }
    .node-hover-preview { position: fixed; width: 220px; border-radius: 14px; overflow: hidden; background: rgba(255,255,255,0.96); box-shadow: 0 18px 42px rgba(15,23,42,0.18); border: 1px solid rgba(148,163,184,0.18); z-index: 3600; pointer-events: none; backdrop-filter: blur(14px); }
    .node-hover-head { padding: 10px 12px; color: #fff; font-weight: 700; }
    .node-hover-body { padding: 12px; display: flex; flex-direction: column; gap: 8px; color: #334155; }
    .node-hover-kind { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #64748b; }
    .node-hover-desc { font-size: 13px; line-height: 1.5; }
    .node-hover-ports { display:flex; gap:10px; font-size:12px; color:#64748b; }
    .submenu-fade-enter-active, .submenu-fade-leave-active { transition: opacity .18s ease, transform .18s cubic-bezier(.2,.9,.2,1) }
    .submenu-fade-enter-from { opacity:0; transform: translateX(-8px) translateY(-4px) scale(.98) }
    .submenu-fade-enter-to { opacity:1; transform: translateX(0) translateY(0) scale(1) }
    .submenu-fade-leave-from { opacity:1; transform: translateX(0) translateY(0) scale(1) }
    .submenu-fade-leave-to { opacity:0; transform: translateX(-6px) translateY(-2px) scale(.99) }
    .ctx-section { border-radius:8px; padding:6px; background:transparent }
    .ctx-section-title { font-weight:700; padding:6px 8px; color:var(--n-text-2); border-bottom:1px dashed rgba(0,0,0,0.04); margin-bottom:6px }
    .ctx-section-items { display:flex; flex-direction:column; gap:6px; padding:4px 6px }
    .ctx-item { padding:8px; border-radius:8px; cursor:pointer; display:flex; flex-direction:column; gap:4px; transition:background .12s ease, transform .06s ease }
    .ctx-item:hover { background:rgba(255,255,255,0.02); transform:translateY(-2px) }
    .ctx-item-title { font-weight:600 }
    .ctx-item-desc { font-size:12px; color:var(--n-text-2); margin-top:4px }
    /* bottom panel styles now scoped to editor layout (absolute) */
    .editor-layout { position:relative; }
    .bottom-panel { position:absolute; left:0; right:0; bottom:0; max-height:360px; transition:max-height .22s ease; z-index:90000; pointer-events:auto; overflow:hidden }
    .bottom-panel.collapsed { max-height:36px }
    .bottom-panel .bottom-panel-handle { background:var(--n-card); padding:8px 12px; border-top:1px solid rgba(0,0,0,0.06); cursor:pointer; width:220px; border-radius:8px 8px 0 0; margin:0 auto; text-align:center }
    .bottom-panel .bottom-panel-body { background: rgba(10,10,10,0.92); display:flex; gap:12px; padding:12px; height:320px; overflow:auto }
    .bottom-left { width:260px; overflow:auto; border-right:1px dashed rgba(255,255,255,0.04); padding-right:8px }
    .bottom-right { flex:1; overflow:auto; padding-left:8px }
    .module-item { padding:6px 8px; cursor:pointer; border-radius:6px }
    .module-item:hover { background: rgba(255,255,255,0.02) }
    .export-item { display:inline-block; padding:4px 6px; margin:4px; background:rgba(255,255,255,0.02); border-radius:4px; cursor:pointer }
    .code-block { background: transparent; color:#e6eef9; padding:8px; border-radius:6px; overflow:auto; max-height:100%; }
    .module-header { font-weight:700; margin-bottom:8px }
    .no-selection { color:var(--n-text-2); padding:12px }
    /* node status indicator */
    .node-indicator { width:14px; height:14px; border-radius:50%; border:1px solid rgba(0,0,0,0.06); box-shadow:0 1px 2px rgba(0,0,0,0.08); }
    .node-indicator.idle { background:#9aa0a6 } /* grey */
    .node-indicator.running { background:#34d399; box-shadow:0 0 8px rgba(52,211,153,0.4) } /* green */
    .node-indicator.error { background:#ff6b6b; box-shadow:0 0 8px rgba(255,107,107,0.35) } /* red */
    .node-indicator.done { background:#4ade80 } /* success */
    /* folder status indicator (same visuals as node) */
    .folder-indicator { width:12px; height:12px; border-radius:50%; border:1px solid rgba(0,0,0,0.06); box-shadow:0 1px 2px rgba(0,0,0,0.08); }
    .folder-indicator.idle { background:#9aa0a6 }
    .folder-indicator.running { background:#34d399; box-shadow:0 0 8px rgba(52,211,153,0.4) }
    .folder-indicator.error { background:#ff6b6b; box-shadow:0 0 8px rgba(255,107,107,0.35) }
    .folder-indicator.done { background:#4ade80 }
    .suggestion-trigger { position: absolute; right: 22px; bottom: 54px; z-index: 92000; }
    .suggestion-list { display:flex; flex-direction:column; gap:12px; }
    .suggestion-item { border-radius: 12px; padding: 12px 14px; border: 1px solid rgba(148,163,184,0.16); background: rgba(248,250,252,0.9); }
    .suggestion-item.error { border-color: rgba(239,68,68,0.24); background: rgba(254,242,242,0.92); }
    .suggestion-item.warning { border-color: rgba(245,158,11,0.24); background: rgba(255,251,235,0.92); }
    .suggestion-title { font-weight: 700; color: #0f172a; margin-bottom: 6px; }
    .suggestion-detail { color: #475569; line-height: 1.6; }
    </style>
