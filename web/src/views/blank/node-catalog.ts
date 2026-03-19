import type { Node } from './editor-core';
import { createBuiltinNode, CUSTOM_NODE_PRESETS, isBuiltinNode } from './node-runtime';
import { KNOWLEDGE_NODE_PRESETS } from './knowledge-pipeline';

export type NodeKind = 'programmable' | 'composite' | 'custom' | 'component';

export type NodePreset = {
  key: string;
  label: string;
  desc: string;
  nodeKind: NodeKind;
  categoryGroup: string;
  inputs?: string[];
  outputs?: string[];
  color?: string;
  code?: string;
  meta?: Record<string, any>;
};

export type WorkflowTemplate = {
  key: string;
  label: string;
  desc: string;
  group: string;
  nodes: Array<{ presetKey: string; dx: number; dy: number; label?: string; code?: string; meta?: Record<string, any>; isInit?: boolean; isOutput?: boolean }>;
  edges: Array<{ from: number; fromPort: number; to: number; toPort: number }>;
};

const PROGRAMMABLE_NODE_PRESETS: NodePreset[] = [
  {
    key: 'const',
    label: '常量',
    desc: '输出固定值',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    outputs: ['value'],
    color: '#FFB86B',
    code: 'res = 42'
  },
  {
    key: 'text',
    label: '文本',
    desc: '输出文本内容',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    outputs: ['text'],
    color: '#FF8AB6',
    code: 'res = "hello world"'
  },
  {
    key: 'add',
    label: '数值相加',
    desc: '进行两个输入的加法',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    inputs: ['a', 'b'],
    outputs: ['res'],
    color: '#9B8CFF',
    code: 'res = a + b'
  },
  {
    key: 'mul',
    label: '数值相乘',
    desc: '进行两个输入的乘法',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    inputs: ['a', 'b'],
    outputs: ['res'],
    color: '#8F6BFF',
    code: 'res = a * b'
  },
  {
    key: 'string-format',
    label: '字符串格式化',
    desc: '使用 Python f-string 组织文本',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    inputs: ['name', 'value'],
    outputs: ['text'],
    color: '#C970D9',
    code: 'res = f"{name}: {value}"'
  },
  {
    key: 'matrix-mul',
    label: '矩阵乘法',
    desc: '矩阵或向量乘法示例',
    nodeKind: 'programmable',
    categoryGroup: 'math',
    inputs: ['left', 'right'],
    outputs: ['matrix'],
    color: '#6E9CF8',
    code: 'import numpy as np\nres = (np.array(left) @ np.array(right)).tolist()'
  },
  {
    key: 'list-map',
    label: '列表映射',
    desc: '遍历列表进行转换',
    nodeKind: 'programmable',
    categoryGroup: 'tooling',
    inputs: ['items'],
    outputs: ['result'],
    color: '#5B8FF9',
    code: 'res = [item for item in (items or [])]'
  },
  {
    key: 'dict-merge',
    label: '对象合并',
    desc: '合并多个字典结构',
    nodeKind: 'programmable',
    categoryGroup: 'tooling',
    inputs: ['left', 'right'],
    outputs: ['merged'],
    color: '#4C9B8A',
    code: 'res = {**(left or {}), **(right or {})}'
  },
  {
    key: 'print',
    label: '输出日志',
    desc: '将输入打印到日志中',
    nodeKind: 'programmable',
    categoryGroup: 'tooling',
    inputs: ['value'],
    outputs: ['value'],
    color: '#6DD98D',
    code: 'print(value)\nres = value'
  }
];

const COMPONENT_NODE_PRESETS: NodePreset[] = [
  {
    key: 'note',
    label: '注释便签',
    desc: '用于说明流程、记录设计备注',
    nodeKind: 'component',
    categoryGroup: 'components',
    color: '#F4C95D',
    meta: {
      note: '在右侧面板编辑便签内容'
    }
  },
  {
    key: 'folder',
    label: '文件夹',
    desc: '组织节点并支持折叠封装',
    nodeKind: 'component',
    categoryGroup: 'components'
  }
];

const CUSTOM_PRESETS: NodePreset[] = CUSTOM_NODE_PRESETS.map(item => ({
  key: item.key,
  label: item.label,
  desc: item.desc,
  nodeKind: 'custom',
  categoryGroup: item.key === 'llm-chat' || item.key === 'agent-task' ? 'llm' : item.key === 'file-read' || item.key === 'file-write' || item.key === 'url-parse' || item.key === 'http-request' ? 'tools' : 'knowledge',
  inputs: item.inputs,
  outputs: item.outputs,
  color: item.color
}));

const KNOWLEDGE_PRESETS: NodePreset[] = KNOWLEDGE_NODE_PRESETS.map(item => ({
  key: item.key,
  label: item.label,
  desc: item.desc,
  nodeKind: 'custom',
  categoryGroup: 'knowledge',
  inputs: item.inputs,
  outputs: item.outputs,
  color: item.color
}));

export const NODE_PRESET_MAP = new Map<string, NodePreset>([
  ...PROGRAMMABLE_NODE_PRESETS,
  ...COMPONENT_NODE_PRESETS,
  ...CUSTOM_PRESETS,
  ...KNOWLEDGE_PRESETS
].map(item => [item.key, item]));

export const NODE_LIBRARY_SECTIONS = [
  {
    key: 'programmable',
    label: '可编程节点',
    items: PROGRAMMABLE_NODE_PRESETS.filter(item => item.categoryGroup === 'math' || item.categoryGroup === 'tooling')
  },
  {
    key: 'tools',
    label: '工具节点',
    items: CUSTOM_PRESETS.filter(item => item.categoryGroup === 'tools')
  },
  {
    key: 'knowledge',
    label: '知识库节点',
    items: [...KNOWLEDGE_PRESETS, ...CUSTOM_PRESETS.filter(item => item.categoryGroup === 'knowledge')]
  },
  {
    key: 'llm',
    label: 'LLM / Agent',
    items: CUSTOM_PRESETS.filter(item => item.categoryGroup === 'llm')
  },
  {
    key: 'components',
    label: '组件节点',
    items: COMPONENT_NODE_PRESETS
  }
];

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    key: 'kb-indexing',
    label: 'PDF知识库入库',
    desc: '完成 PDF 解析、分块、向量化与索引检索',
    group: 'knowledge',
    nodes: [
      { presetKey: 'pdf-parse', dx: 0, dy: 0, isInit: true },
      { presetKey: 'chunk-split', dx: 260, dy: 0 },
      { presetKey: 'api-embedding', dx: 520, dy: 0 },
      { presetKey: 'index-search', dx: 780, dy: 0, isOutput: true }
    ],
    edges: [
      { from: 0, fromPort: 0, to: 1, toPort: 0 },
      { from: 1, fromPort: 0, to: 2, toPort: 0 },
      { from: 2, fromPort: 0, to: 3, toPort: 0 }
    ]
  },
  {
    key: 'http-llm-summary',
    label: 'HTTP抓取后总结',
    desc: '请求远程数据后交给 LLM 总结',
    group: 'llm',
    nodes: [
      { presetKey: 'http-request', dx: 0, dy: 0, isInit: true },
      { presetKey: 'llm-chat', dx: 280, dy: 0, isOutput: true }
    ],
    edges: [{ from: 0, fromPort: 0, to: 1, toPort: 1 }]
  },
  {
    key: 'agent-research',
    label: 'Agent任务分析',
    desc: '围绕任务输入进行规划与结果输出',
    group: 'llm',
    nodes: [
      { presetKey: 'text', dx: 0, dy: 0, label: '任务输入', code: 'res = "为一个新知识库项目生成实施计划"', isInit: true },
      { presetKey: 'agent-task', dx: 260, dy: 0, isOutput: true }
    ],
    edges: [{ from: 0, fromPort: 0, to: 1, toPort: 0 }]
  },
  {
    key: 'matrix-lab',
    label: '矩阵运算实验',
    desc: '快速试验矩阵乘法和结果打印',
    group: 'programmable',
    nodes: [
      { presetKey: 'const', dx: 0, dy: 0, label: '矩阵A', code: 'res = [[1, 2], [3, 4]]', isInit: true },
      { presetKey: 'const', dx: 0, dy: 160, label: '矩阵B', code: 'res = [[5], [6]]', isInit: true },
      { presetKey: 'matrix-mul', dx: 260, dy: 80 },
      { presetKey: 'print', dx: 520, dy: 80, isOutput: true }
    ],
    edges: [
      { from: 0, fromPort: 0, to: 2, toPort: 0 },
      { from: 1, fromPort: 0, to: 2, toPort: 1 },
      { from: 2, fromPort: 0, to: 3, toPort: 0 }
    ]
  },
  {
    key: 'url-debug',
    label: 'URL分析模板',
    desc: '输入 URL 并查看解析结果',
    group: 'tools',
    nodes: [
      { presetKey: 'text', dx: 0, dy: 0, label: 'URL输入', code: 'res = "https://example.com/docs?page=2&lang=zh#intro"', isInit: true },
      { presetKey: 'url-parse', dx: 260, dy: 0, isOutput: true }
    ],
    edges: [{ from: 0, fromPort: 0, to: 1, toPort: 0 }]
  }
];

export const WORKFLOW_TEMPLATE_GROUPS = [
  { key: 'programmable', label: '可编程模板' },
  { key: 'tools', label: '工具模板' },
  { key: 'knowledge', label: '知识库模板' },
  { key: 'llm', label: 'LLM / Agent 模板' }
];

export function createNodeFromPreset(presetKey: string, id: string, x: number, y: number): Node | null {
  const preset = NODE_PRESET_MAP.get(presetKey);
  if (!preset) return null;
  if (preset.key === 'folder') return null;
  if (isBuiltinNode(preset.key)) return createBuiltinNode(preset.key, id, x, y);
  if (preset.key === 'note') {
    return {
      id,
      x,
      y,
      label: preset.label,
      category: 'note',
      inputs: [],
      outputs: [],
      inputTypes: [],
      outputTypes: [],
      code: '',
      color: preset.color,
      lastResult: null,
      meta: {
        nodeKind: 'component',
        description: preset.desc,
        note: preset.meta?.note || '',
        template: { kind: 'note', version: '1.0.0' },
        community: { shareId: '', visibility: 'private', tags: ['note'] }
      }
    };
  }
  return {
    id,
    x,
    y,
    label: preset.label,
    category: preset.key,
    inputs: [...(preset.inputs || [])],
    outputs: [...(preset.outputs || [])],
    inputTypes: (preset.inputs || []).map(() => 'Any'),
    outputTypes: (preset.outputs || []).map(() => 'Any'),
    code: preset.code || '',
    color: preset.color,
    lastResult: null,
    meta: {
      nodeKind: preset.nodeKind,
      description: preset.desc,
      template: { kind: 'built-in', version: '1.0.0' },
      community: { shareId: '', visibility: 'private', tags: [preset.key] }
    }
  };
}

export function getNodePreset(presetKey?: string) {
  if (!presetKey) return null;
  return NODE_PRESET_MAP.get(presetKey) || null;
}
