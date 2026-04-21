import type { Node } from './editor-core';
import {
  createKnowledgeNode,
  getKnowledgeNodeConfigText,
  isKnowledgeNode,
  KNOWLEDGE_NODE_PRESETS,
  runKnowledgeNode
} from './knowledge-pipeline';

export type CustomNodeCategory =
  | 'file-read'
  | 'file-write'
  | 'url-parse'
  | 'http-request'
  | 'llm-chat'
  | 'agent-task'
  | 'agent-orchestrator';

export type BuiltinNodeCategory = CustomNodeCategory | (typeof KNOWLEDGE_NODE_PRESETS)[number]['key'];

type CustomPreset = {
  key: CustomNodeCategory;
  label: string;
  desc: string;
  inputs: string[];
  outputs: string[];
  color: string;
  config: Record<string, any>;
};

export const CUSTOM_NODE_PRESETS: CustomPreset[] = [
  {
    key: 'file-read',
    label: '文件读取',
    desc: '读取上传文件或上游 File 的文本内容',
    inputs: ['file'],
    outputs: ['content'],
    color: '#4F8EF7',
    config: { mode: 'text', encoding: 'utf-8' }
  },
  {
    key: 'file-write',
    label: '文件写出',
    desc: '将内容保存为本地文件下载',
    inputs: ['content', 'filename'],
    outputs: ['fileInfo'],
    color: '#3BA272',
    config: { defaultFileName: 'output.txt', mimeType: 'text/plain;charset=utf-8' }
  },
  {
    key: 'url-parse',
    label: 'URL解析',
    desc: '解析 URL、查询参数与路径信息',
    inputs: ['url'],
    outputs: ['parts'],
    color: '#EEA33C',
    config: {}
  },
  {
    key: 'http-request',
    label: 'HTTP请求',
    desc: '发起 HTTP 请求并返回响应结果',
    inputs: ['url', 'body'],
    outputs: ['response'],
    color: '#D96C6C',
    config: { method: 'GET', headers: {}, responseType: 'json' }
  },
  {
    key: 'llm-chat',
    label: 'LLM问答',
    desc: '通过 API 调用大模型完成问答',
    inputs: ['prompt', 'context'],
    outputs: ['answer'],
    color: '#8A63D2',
    config: {
      endpoint: '',
      apiKey: '',
      model: '',
      method: 'POST',
      headers: {},
      inputMode: 'chat',
      systemPrompt: '',
      temperature: 0.2
    }
  },
  {
    key: 'agent-task',
    label: 'Agent任务',
    desc: '面向任务的多步规划与执行提示节点',
    inputs: ['task', 'context'],
    outputs: ['result'],
    color: '#5B8FF9',
    config: {
      endpoint: '',
      apiKey: '',
      model: '',
      method: 'POST',
      headers: {},
      systemPrompt: '你是一个善于规划与执行的智能代理，请给出清晰的步骤和最终结果。',
      temperature: 0.3
    }
  },
  {
    key: 'agent-orchestrator',
    label: 'Agent Orchestrator',
    desc: 'Run a local multi-step agent loop with plan, action, reflection and summary',
    inputs: ['task', 'context', 'toolHints'],
    outputs: ['agentState', 'finalAnswer'],
    color: '#3F7AE0',
    config: {
      strategy: 'plan-act-reflect',
      maxIterations: 3,
      includeEvidence: true
    }
  }
];

export function isCustomNode(category?: string): category is CustomNodeCategory {
  return CUSTOM_NODE_PRESETS.some(item => item.key === category);
}

export function isBuiltinNode(category?: string): category is BuiltinNodeCategory {
  return isKnowledgeNode(category) || isCustomNode(category);
}

export function getBuiltinNodeConfigText(node: Node | null | undefined) {
  if (!node || !isBuiltinNode(node.category)) return '';
  if (isKnowledgeNode(node.category)) return getKnowledgeNodeConfigText(node);
  return JSON.stringify(node.meta?.config || {}, null, 2);
}

export function createBuiltinNode(category: BuiltinNodeCategory, id: string, x: number, y: number): Node {
  if (isKnowledgeNode(category)) return createKnowledgeNode(category, id, x, y);

  const preset = CUSTOM_NODE_PRESETS.find(item => item.key === category);
  if (!preset) throw new Error(`Unknown builtin category: ${category}`);

  return {
    id,
    x,
    y,
    label: preset.label,
    category: preset.key,
    inputs: [...preset.inputs],
    outputs: [...preset.outputs],
    inputTypes: preset.inputs.map(() => 'Any'),
    outputTypes: preset.outputs.map(() => 'Any'),
    code: '',
    color: preset.color,
    lastResult: null,
    meta: {
      builtin: true,
      nodeKind: 'custom',
      description: preset.desc,
      config: JSON.parse(JSON.stringify(preset.config)),
      template: { kind: 'built-in', version: '1.0.0' },
      community: {
        shareId: '',
        slug: '',
        author: '',
        tags: [preset.key],
        visibility: 'private',
        stats: { downloads: 0, likes: 0, forks: 0 }
      }
    },
    resources: []
  };
}

export async function runBuiltinNode(node: Node, inputs: any[], envEntries?: Array<{ key: string; value: string; secret?: boolean }>) {
  const env = Object.fromEntries((envEntries || []).filter(item => item.key).map(item => [item.key, item.value]));
  if (isKnowledgeNode(node.category)) {
    const resolvedNode = {
      ...node,
      meta: {
        ...(node.meta || {}),
        config: resolveEnvInObject(node.meta?.config || {}, env)
      }
    } as Node;
    return runKnowledgeNode(resolvedNode, inputs);
  }
  if (!isCustomNode(node.category)) {
    throw new Error(`Unsupported builtin node: ${String(node.category)}`);
  }
  const config = resolveEnvInObject(node.meta?.config || {}, env);

  if (node.category === 'file-read') return runFileRead(node, inputs);
  if (node.category === 'file-write') return runFileWrite(inputs, config);
  if (node.category === 'url-parse') return runUrlParse(inputs[0]);
  if (node.category === 'http-request') return runHttpRequest(inputs, config);
  if (node.category === 'llm-chat') return runLlmChat(inputs, config);
  if (node.category === 'agent-task') return runAgentTask(inputs, config);
  if (node.category === 'agent-orchestrator') return runAgentOrchestrator(inputs, config);

  throw new Error(`Unsupported custom node: ${String(node.category)}`);
}

async function runFileRead(node: Node, inputs: any[]) {
  const files = [...normalizeFiles(inputs[0]), ...normalizeFiles(node.resources)];
  if (!files.length) throw new Error('文件读取节点未找到可读取文件');

  const results = await Promise.all(files.map(async file => {
    const text = await file.text();
    return {
      name: file.name,
      size: file.size,
      type: file.type,
      text,
      json: tryParseJson(text)
    };
  }));

  return { type: 'file-content', files: results };
}

async function runFileWrite(inputs: any[], config: Record<string, any>) {
  const content = inputs[0] == null ? '' : typeof inputs[0] === 'string' ? inputs[0] : JSON.stringify(inputs[0], null, 2);
  const filename = String(inputs[1] || config.defaultFileName || 'output.txt');
  const mimeType = String(config.mimeType || 'text/plain;charset=utf-8');
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    try { link.remove(); } catch {}
  }, 3000);
  return { type: 'file-write', filename, size: blob.size, mimeType };
}

function runUrlParse(input: any) {
  const raw = typeof input === 'string' ? input : input?.url;
  if (!raw) throw new Error('URL解析节点需要 url 输入');
  const url = new URL(raw);
  return {
    type: 'url-parts',
    href: url.href,
    origin: url.origin,
    protocol: url.protocol,
    host: url.host,
    pathname: url.pathname,
    search: url.search,
    hash: url.hash,
    params: Object.fromEntries(url.searchParams.entries())
  };
}

async function runHttpRequest(inputs: any[], config: Record<string, any>) {
  const url = String(inputs[0] || config.url || '').trim();
  if (!url) throw new Error('HTTP请求节点缺少 URL');
  const method = String(config.method || 'GET').toUpperCase();
  const headers = normalizeHeaders(config.headers);
  let body: BodyInit | undefined;
  const inputBody = inputs[1] ?? config.body;
  if (inputBody != null && method !== 'GET') {
    body = typeof inputBody === 'string' ? inputBody : JSON.stringify(inputBody);
    if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(url, { method, headers, body });
  const responseType = String(config.responseType || 'json');
  const text = await response.text();
  const headerEntries: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    headerEntries[key] = value;
  });
  return {
    type: 'http-response',
    ok: response.ok,
    status: response.status,
    headers: headerEntries,
    text,
    data: responseType === 'json' ? tryParseJson(text) ?? text : text
  };
}

async function runLlmChat(inputs: any[], config: Record<string, any>) {
  const prompt = String(inputs[0] || '').trim();
  const context = inputs[1];
  if (!prompt) throw new Error('LLM问答节点需要 prompt 输入');
  const payload = buildLlmPayload(prompt, context, config, false);
  const data = await callModelApi(payload, config);
  return {
    type: 'llm-answer',
    answer: extractModelText(data, config.responsePath),
    raw: data
  };
}

async function runAgentTask(inputs: any[], config: Record<string, any>) {
  const task = String(inputs[0] || '').trim();
  const context = inputs[1];
  if (!task) throw new Error('Agent任务节点需要 task 输入');
  const prompt = `请将下面任务拆解为步骤，并在最后给出可执行结论。\n\n任务:\n${task}`;
  const payload = buildLlmPayload(prompt, context, config, true);
  const data = await callModelApi(payload, config);
  return {
    type: 'agent-result',
    result: extractModelText(data, config.responsePath),
    raw: data
  };
}

function runAgentOrchestrator(inputs: any[], config: Record<string, any>) {
  const task = String(inputs[0] || '').trim();
  const context = inputs[1];
  const toolHints = inputs[2];
  if (!task) throw new Error('Agent Orchestrator requires task input');

  const maxIterationsRaw = Number(config.maxIterations ?? 3);
  const maxIterations = Number.isFinite(maxIterationsRaw)
    ? Math.max(1, Math.min(8, Math.trunc(maxIterationsRaw)))
    : 3;
  const strategy = String(config.strategy || 'plan-act-reflect');
  const includeEvidence = Boolean(config.includeEvidence ?? true);

  const plan = task
    .split(/[\n.;，。！？!?\-]+/)
    .map(item => item.trim())
    .filter(Boolean)
    .slice(0, maxIterations);

  if (!plan.length) {
    plan.push(`Analyze task intent: ${task}`, 'Build an execution plan', 'Draft final answer');
  }

  const contextPreview =
    context == null
      ? 'none'
      : typeof context === 'string'
        ? context.slice(0, 180)
        : JSON.stringify(context).slice(0, 180);

  const toolPreview =
    toolHints == null
      ? 'none'
      : typeof toolHints === 'string'
        ? toolHints.slice(0, 180)
        : JSON.stringify(toolHints).slice(0, 180);

  const iterations = plan.slice(0, maxIterations).map((step, index) => {
    const n = index + 1;
    return {
      iteration: n,
      thought: `Step ${n}: ${step}`,
      action: `Use strategy=${strategy} to execute this step`,
      observation: includeEvidence
        ? `Context sample=${contextPreview}; Tool hints=${toolPreview}`
        : 'Evidence omitted by config'
    };
  });

  const summary = [
    `Task: ${task}`,
    `Strategy: ${strategy}`,
    `Iterations: ${iterations.length}`,
    `Conclusion: execution plan completed`
  ].join('\n');

  return {
    type: 'agent-orchestrator',
    task,
    strategy,
    plan,
    iterations,
    final: {
      status: 'completed',
      answer: summary,
      confidence: Math.max(0.55, Math.min(0.92, 0.6 + iterations.length * 0.08))
    },
    metrics: {
      maxIterations,
      executedIterations: iterations.length
    }
  };
}

function buildLlmPayload(prompt: string, context: any, config: Record<string, any>, agentMode: boolean) {
  const model = config.model;
  const systemPrompt = String(config.systemPrompt || '').trim();
  const messages = [];
  if (systemPrompt) messages.push({ role: 'system', content: systemPrompt });
  if (context != null && context !== '') {
    messages.push({ role: 'user', content: `上下文:\n${typeof context === 'string' ? context : JSON.stringify(context, null, 2)}` });
  }
  messages.push({ role: 'user', content: agentMode ? `${prompt}\n\n请返回结构清晰的结果。` : prompt });
  return {
    model,
    temperature: Number(config.temperature ?? 0.2),
    messages
  };
}

async function callModelApi(payload: Record<string, any>, config: Record<string, any>) {
  const endpoint = String(config.endpoint || '').trim();
  if (!endpoint) throw new Error('模型节点缺少 endpoint 配置');
  const method = String(config.method || 'POST').toUpperCase();
  const headers = {
    'Content-Type': 'application/json',
    ...normalizeHeaders(config.headers)
  } as Record<string, string>;
  if (config.apiKey) {
    headers.Authorization = headers.Authorization || `Bearer ${config.apiKey}`;
    headers['api-key'] = headers['api-key'] || config.apiKey;
  }
  const response = await fetch(endpoint, {
    method,
    headers,
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`模型调用失败: ${response.status} ${text}`);
  }
  return response.json();
}

function extractModelText(data: any, responsePath?: string) {
  const selected = responsePath ? getValueByPath(data, String(responsePath)) : undefined;
  const selectedText = normalizeModelText(selected);
  if (selectedText) return selectedText;

  const outputText = normalizeModelText(data?.output_text);
  if (outputText) return outputText;

  const choiceText = normalizeModelText(data?.choices?.[0]?.message?.content);
  if (choiceText) return choiceText;

  const contentText = normalizeModelText(data?.content);
  if (contentText) return contentText;

  const responseText = normalizeModelText(data?.output);
  if (responseText) return responseText;

  return JSON.stringify(data, null, 2);
}

function resolveEnvInObject(value: any, env: Record<string, string>): any {
  if (typeof value === 'string') {
    return value.replace(/\$\{([A-Z0-9_]+)\}/gi, (_, key) => env[key] ?? '');
  }
  if (Array.isArray(value)) return value.map(item => resolveEnvInObject(item, env));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolveEnvInObject(item, env)]));
  }
  return value;
}

function normalizeHeaders(value: any) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function normalizeFiles(input: any): File[] {
  if (!input) return [];
  if (input instanceof File) return [input];
  if (Array.isArray(input)) return input.filter((item): item is File => item instanceof File);
  if (Array.isArray(input?.files)) return input.files.filter((item: any): item is File => item instanceof File);
  if (input?.file instanceof File) return [input.file];
  return [];
}

function tryParseJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function isPlainObject(value: any): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function getValueByPath(source: any, rawPath: string) {
  const path = String(rawPath || '').trim();
  if (!path) return undefined;
  return path.split('.').reduce((current, segment) => {
    if (current == null) return undefined;
    if (/^\d+$/.test(segment)) return current[Number(segment)];
    return current[segment];
  }, source);
}

function normalizeModelText(value: any): string {
  if (typeof value === 'string') return value;
  if (!value) return '';
  if (Array.isArray(value)) {
    return value.map(item => normalizeModelText(item)).filter(Boolean).join('\n').trim();
  }
  if (typeof value?.text === 'string') return value.text;
  if (Array.isArray(value?.content)) return normalizeModelText(value.content);
  return '';
}
