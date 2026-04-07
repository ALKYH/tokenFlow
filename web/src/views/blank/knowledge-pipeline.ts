import type { Node } from './editor-core';

declare global {
  interface Window {
    pdfjsLib?: any;
  }
}

export type KnowledgeNodeCategory =
  | 'pdf-parse'
  | 'chunk-split'
  | 'var-merge'
  | 'api-embedding'
  | 'keyword-search'
  | 'index-search';

type KnowledgeDocument = {
  id: string;
  fileId: string;
  fileName: string;
  text: string;
  pages: Array<{ pageNumber: number; text: string }>;
  metadata?: Record<string, any>;
};

type KnowledgeChunk = {
  id: string;
  fileId: string;
  fileName: string;
  text: string;
  page?: number;
  chunkIndex: number;
  metadata?: Record<string, any>;
  embedding?: number[];
};

type KnowledgeIndex = {
  type: 'knowledge-index';
  provider: string;
  generatedAt: string;
  dimension: number;
  files: Array<{ fileId: string; fileName: string; chunkCount: number }>;
  chunks: KnowledgeChunk[];
  embeddingConfig?: Record<string, any>;
};

type BuiltinPreset = {
  key: KnowledgeNodeCategory;
  label: string;
  desc: string;
  inputs: string[];
  outputs: string[];
  color: string;
  config: Record<string, any>;
};

const PDFJS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js';
const PDFJS_WORKER_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';

export const KNOWLEDGE_NODE_PRESETS: BuiltinPreset[] = [
  {
    key: 'pdf-parse',
    label: 'PDF解析',
    desc: '导入 PDF 并提取页文本',
    inputs: ['file'],
    outputs: ['documents'],
    color: '#F08A5D',
    config: { joinPages: true, maxPages: 0 }
  },
  {
    key: 'chunk-split',
    label: '分块',
    desc: '将文档切分为知识块',
    inputs: ['source'],
    outputs: ['chunks'],
    color: '#4C9B8A',
    config: { chunkSize: 800, chunkOverlap: 120, keepPageNumber: true }
  },
  {
    key: 'var-merge',
    label: '变量聚合',
    desc: '聚合上游变量并补充元数据',
    inputs: ['source', 'metadata'],
    outputs: ['merged'],
    color: '#5B8FF9',
    config: { mode: 'smart' }
  },
  {
    key: 'api-embedding',
    label: 'API Embedding',
    desc: '调用外部 Embedding API 建立索引',
    inputs: ['chunks'],
    outputs: ['index'],
    color: '#8A63D2',
    config: {
      endpoint: '',
      apiKey: '',
      model: '',
      method: 'POST',
      inputField: 'input',
      modelField: 'model',
      headers: {},
      batchSize: 8
    }
  },
  {
    key: 'keyword-search',
    label: '关键词检索',
    desc: '基于关键词在索引或分块中搜索',
    inputs: ['source', 'query'],
    outputs: ['matches'],
    color: '#E6A23C',
    config: { topK: 5, minScore: 0 }
  },
  {
    key: 'index-search',
    label: '索引检索',
    desc: '对向量索引执行语义检索',
    inputs: ['index', 'query'],
    outputs: ['matches'],
    color: '#D96C6C',
    config: {
      topK: 5,
      minScore: 0,
      endpoint: '',
      apiKey: '',
      model: '',
      method: 'POST',
      inputField: 'input',
      modelField: 'model',
      headers: {}
    }
  }
];

export function isKnowledgeNode(category?: string): category is KnowledgeNodeCategory {
  return KNOWLEDGE_NODE_PRESETS.some(item => item.key === category);
}

export function getKnowledgeNodePreset(category?: string) {
  return KNOWLEDGE_NODE_PRESETS.find(item => item.key === category);
}

export function createKnowledgeNode(category: KnowledgeNodeCategory, id: string, x: number, y: number): Node {
  const preset = getKnowledgeNodePreset(category);
  if (!preset) {
    throw new Error(`Unknown knowledge node category: ${category}`);
  }

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
      config: cloneValue(preset.config),
      template: {
        kind: 'built-in',
        version: '1.0.0'
      },
      community: {
        shareId: '',
        slug: '',
        author: '',
        tags: [preset.key],
        visibility: 'private',
        stats: {
          downloads: 0,
          likes: 0,
          forks: 0
        }
      }
    },
    resources: []
  };
}

export function getKnowledgeNodeConfigText(node: Node | null | undefined) {
  if (!node || !isKnowledgeNode(node.category)) return '';
  return JSON.stringify(node.meta?.config || {}, null, 2);
}

export async function runKnowledgeNode(node: Node, inputs: any[]) {
  const category = node.category as KnowledgeNodeCategory;
  const config = node.meta?.config || {};

  if (category === 'pdf-parse') {
    return runPdfParser(node, inputs, config);
  }
  if (category === 'chunk-split') {
    return runChunker(inputs[0], config);
  }
  if (category === 'var-merge') {
    return runVariableMerge(node, inputs, config);
  }
  if (category === 'api-embedding') {
    return runEmbeddingIndex(inputs[0], config);
  }
  if (category === 'keyword-search') {
    return runKeywordSearch(inputs[0], inputs[1], config);
  }
  if (category === 'index-search') {
    return runIndexSearch(inputs[0], inputs[1], config);
  }

  throw new Error(`Unsupported knowledge node category: ${String(category)}`);
}

async function ensurePdfJs() {
  if (window.pdfjsLib) return window.pdfjsLib;

  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector(`script[src="${PDFJS_SRC}"]`) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error('pdf.js load failed')), { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = PDFJS_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('pdf.js load failed'));
    document.head.appendChild(script);
  });

  if (!window.pdfjsLib) {
    throw new Error('pdf.js is not available');
  }

  window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_SRC;
  return window.pdfjsLib;
}

async function runPdfParser(node: Node, inputs: any[], config: Record<string, any>) {
  const attachedFiles = (node.resources || [])
    .map(item => item.file)
    .filter((file): file is File => file instanceof File);
  const inboundFiles = normalizeFiles(inputs[0]);
  const files = [...inboundFiles, ...attachedFiles];

  if (!files.length) {
    throw new Error('PDF解析节点未找到可用文件，请在节点配置中上传 PDF，或从上游传入 File');
  }

  const pdfjsLib = await ensurePdfJs();
  const documents: KnowledgeDocument[] = [];
  const maxPages = Number(config.maxPages || 0);

  for (const file of files) {
    const buffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
    const pageCount = maxPages > 0 ? Math.min(pdf.numPages, maxPages) : pdf.numPages;
    const pages: Array<{ pageNumber: number; text: string }> = [];

    for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const content = await page.getTextContent();
      const text = (content.items || [])
        .map((item: any) => ('str' in item ? item.str : ''))
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
      pages.push({ pageNumber, text });
    }

    documents.push({
      id: createId('doc'),
      fileId: createId(`file_${file.name}`),
      fileName: file.name,
      text: config.joinPages === false ? pages.map(page => `[Page ${page.pageNumber}] ${page.text}`).join('\n') : pages.map(page => page.text).join('\n'),
      pages
    });
  }

  return {
    type: 'documents',
    count: documents.length,
    documents
  };
}

function runChunker(source: any, config: Record<string, any>) {
  const chunkSize = Math.max(50, Number(config.chunkSize || 800));
  const chunkOverlap = Math.max(0, Math.min(chunkSize - 1, Number(config.chunkOverlap || 120)));
  const documents = normalizeDocuments(source);

  if (!documents.length) {
    throw new Error('分块节点需要文档、文本或 PDF 解析输出');
  }

  const chunks: KnowledgeChunk[] = [];

  for (const doc of documents) {
    const pageAwareChunks = createChunksFromDocument(doc, chunkSize, chunkOverlap, config.keepPageNumber !== false);
    chunks.push(...pageAwareChunks);
  }

  return {
    type: 'chunks',
    count: chunks.length,
    chunks
  };
}

function runVariableMerge(node: Node, inputs: any[], config: Record<string, any>) {
  const entries = (node.inputs || []).map((name, index) => ({
    key: (name || `input_${index + 1}`).trim() || `input_${index + 1}`,
    value: inputs[index]
  })).filter(item => item.value !== null && item.value !== undefined);

  if (!entries.length) {
    return { type: 'merged', value: null };
  }

  const primary = entries[0]?.value;
  const secondary = entries[1]?.value;

  if (config.mode === 'smart' && Array.isArray(primary) && secondary && typeof secondary === 'object' && !Array.isArray(secondary)) {
    return {
      type: 'merged',
      value: primary.map((item, index) => {
        if (item && typeof item === 'object' && !Array.isArray(item)) {
          return { ...item, ...secondary };
        }
        return { value: item, index, ...secondary };
      })
    };
  }

  if (config.mode === 'smart' && isPlainObject(primary) && isPlainObject(secondary)) {
    return {
      type: 'merged',
      value: { ...primary, ...secondary }
    };
  }

  return {
    type: 'merged',
    value: Object.fromEntries(entries.map(item => [item.key, item.value]))
  };
}

async function runEmbeddingIndex(source: any, config: Record<string, any>) {
  const chunks = normalizeChunks(source);
  if (!chunks.length) {
    throw new Error('Embedding 节点需要分块结果或包含 text 的数组');
  }

  const batchSize = Math.max(1, Number(config.batchSize || 8));
  const indexedChunks: KnowledgeChunk[] = [];

  for (let index = 0; index < chunks.length; index += batchSize) {
    const batch = chunks.slice(index, index + batchSize);
    const vectors = await requestEmbeddings(batch.map(item => item.text), config);

    batch.forEach((item, offset) => {
      indexedChunks.push({
        ...item,
        embedding: vectors[offset]
      });
    });
  }

  const fileMap = new Map<string, { fileId: string; fileName: string; chunkCount: number }>();
  indexedChunks.forEach(chunk => {
    const prev = fileMap.get(chunk.fileId) || { fileId: chunk.fileId, fileName: chunk.fileName, chunkCount: 0 };
    prev.chunkCount += 1;
    fileMap.set(chunk.fileId, prev);
  });

  const index = {
    type: 'knowledge-index',
    provider: 'api-embedding',
    generatedAt: new Date().toISOString(),
    dimension: indexedChunks[0]?.embedding?.length || 0,
    files: Array.from(fileMap.values()),
    chunks: indexedChunks,
    embeddingConfig: sanitizeEmbeddingConfig(config)
  } satisfies KnowledgeIndex;

  return attachRuntimeEmbeddingConfig(index, config);
}

function runKeywordSearch(source: any, queryInput: any, config: Record<string, any>) {
  const query = extractQuery(queryInput, config);
  if (!query) {
    throw new Error('关键词检索节点需要 query 输入或在配置中提供 query');
  }

  const chunks = normalizeChunks(source);
  if (!chunks.length) {
    throw new Error('关键词检索节点需要索引、分块结果或文档');
  }

  const queryTokens = tokenize(query);
  const topK = Math.max(1, Number(config.topK || 5));
  const minScore = Number(config.minScore || 0);

  const matches = chunks
    .map(chunk => {
      const haystackTokens = tokenize(`${chunk.fileName} ${chunk.text}`);
      const tokenSet = new Set(haystackTokens);
      const hits = queryTokens.filter(token => tokenSet.has(token)).length;
      const score = queryTokens.length ? hits / queryTokens.length : 0;
      return { score, chunk };
    })
    .filter(item => item.score >= minScore && item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)
    .map(item => ({
      score: Number(item.score.toFixed(4)),
      fileName: item.chunk.fileName,
      page: item.chunk.page,
      text: item.chunk.text,
      chunkId: item.chunk.id,
      metadata: item.chunk.metadata || {}
    }));

  return {
    type: 'keyword-matches',
    query,
    total: matches.length,
    matches
  };
}

async function runIndexSearch(indexInput: any, queryInput: any, config: Record<string, any>) {
  const index = normalizeIndex(indexInput);
  if (!index) {
    throw new Error('索引检索节点需要来自 Embedding 节点的索引输入');
  }

  const queryEmbedding = await resolveQueryEmbedding(queryInput, config, index);
  const topK = Math.max(1, Number(config.topK || 5));
  const minScore = Number(config.minScore || 0);

  const matches = index.chunks
    .filter(chunk => Array.isArray(chunk.embedding) && chunk.embedding.length)
    .map(chunk => ({
      score: cosineSimilarity(queryEmbedding, chunk.embedding || []),
      chunk
    }))
    .filter(item => item.score >= minScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)
    .map(item => ({
      score: Number(item.score.toFixed(4)),
      fileName: item.chunk.fileName,
      page: item.chunk.page,
      text: item.chunk.text,
      chunkId: item.chunk.id,
      metadata: item.chunk.metadata || {}
    }));

  return {
    type: 'index-matches',
    query: extractQuery(queryInput, config),
    total: matches.length,
    matches
  };
}

async function requestEmbeddings(texts: string[], config: Record<string, any>) {
  const endpoint = String(config.endpoint || '').trim();
  if (!endpoint) {
    throw new Error('Embedding API 节点缺少 endpoint 配置');
  }

  const method = String(config.method || 'POST').toUpperCase();
  const payload: Record<string, any> = {};
  const inputField = String(config.inputField || 'input');
  const modelField = String(config.modelField || 'model');
  payload[inputField] = texts.length === 1 ? texts[0] : texts;
  if (config.model) {
    payload[modelField] = config.model;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(normalizeHeaders(config.headers))
  };

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
    const message = await response.text();
    throw new Error(`Embedding API 请求失败: ${response.status} ${message}`);
  }

  const data = await response.json();
  const embeddings = extractEmbeddings(data);

  if (!embeddings.length) {
    throw new Error('Embedding API 返回中未找到 embedding 向量');
  }

  if (embeddings.length !== texts.length) {
    throw new Error(`Embedding API returned ${embeddings.length} vectors for ${texts.length} inputs`);
  }

  return embeddings;
}

function extractEmbeddings(data: any): number[][] {
  if (Array.isArray(data?.data)) {
    return data.data
      .map((item: any) => item?.embedding)
      .filter((item: any) => Array.isArray(item));
  }

  if (Array.isArray(data?.embeddings)) {
    return data.embeddings.filter((item: any) => Array.isArray(item));
  }

  if (Array.isArray(data?.result?.data)) {
    return data.result.data
      .map((item: any) => item?.embedding)
      .filter((item: any) => Array.isArray(item));
  }

  return [];
}

function normalizeHeaders(value: any) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function sanitizeEmbeddingConfig(config: Record<string, any>) {
  const clone = cloneValue(config);
  if (clone.apiKey) clone.apiKey = '***';
  return clone;
}

function attachRuntimeEmbeddingConfig<T extends KnowledgeIndex>(index: T, config: Record<string, any>) {
  try {
    Object.defineProperty(index, '__runtimeEmbeddingConfig', {
      value: cloneValue(config),
      enumerable: false,
      configurable: true
    });
  } catch {}
  return index;
}

function getRuntimeEmbeddingConfig(index: KnowledgeIndex | null | undefined) {
  const runtimeConfig = (index as any)?.__runtimeEmbeddingConfig;
  return isPlainObject(runtimeConfig) ? runtimeConfig : {};
}

function normalizeFiles(input: any): File[] {
  if (!input) return [];
  if (input instanceof File) return [input];
  if (Array.isArray(input)) return input.filter((item): item is File => item instanceof File);
  if (Array.isArray(input?.files)) return input.files.filter((item: any): item is File => item instanceof File);
  if (input?.file instanceof File) return [input.file];
  return [];
}

function normalizeDocuments(source: any): KnowledgeDocument[] {
  if (!source) return [];
  if (typeof source === 'string') {
    return [{
      id: createId('doc'),
      fileId: createId('text'),
      fileName: 'inline.txt',
      text: source,
      pages: [{ pageNumber: 1, text: source }]
    }];
  }

  if (Array.isArray(source)) {
    if (source.every(item => typeof item === 'string')) {
      return source.map((text, index) => ({
        id: createId(`doc_${index}`),
        fileId: createId(`text_${index}`),
        fileName: `inline-${index + 1}.txt`,
        text,
        pages: [{ pageNumber: 1, text }]
      }));
    }

    if (source.every(item => typeof item?.text === 'string')) {
      return source.map((item, index) => ({
        id: item.id || createId(`doc_${index}`),
        fileId: item.fileId || createId(item.fileName || `file_${index}`),
        fileName: item.fileName || `document-${index + 1}.txt`,
        text: item.text,
        pages: Array.isArray(item.pages) && item.pages.length ? item.pages : [{ pageNumber: 1, text: item.text }],
        metadata: item.metadata || {}
      }));
    }
  }

  if (Array.isArray(source?.documents)) {
    return normalizeDocuments(source.documents);
  }

  if (Array.isArray(source?.chunks)) {
    const grouped = new Map<string, KnowledgeDocument>();
    normalizeChunks(source).forEach(chunk => {
      const current = grouped.get(chunk.fileId) || {
        id: createId(`doc_${chunk.fileId}`),
        fileId: chunk.fileId,
        fileName: chunk.fileName,
        text: '',
        pages: [],
        metadata: chunk.metadata || {}
      };
      current.text = current.text ? `${current.text}\n${chunk.text}` : chunk.text;
      current.pages.push({ pageNumber: chunk.page || current.pages.length + 1, text: chunk.text });
      grouped.set(chunk.fileId, current);
    });
    return Array.from(grouped.values());
  }

  if (typeof source?.text === 'string') {
    return normalizeDocuments([source]);
  }

  return [];
}

function normalizeChunks(source: any): KnowledgeChunk[] {
  if (!source) return [];

  if (Array.isArray(source) && source.every(item => typeof item?.text === 'string')) {
    return source.map((item, index) => ({
      id: item.id || createId(`chunk_${index}`),
      fileId: item.fileId || createId(item.fileName || `source_${index}`),
      fileName: item.fileName || `chunk-source-${index + 1}.txt`,
      text: item.text,
      page: item.page,
      chunkIndex: Number(item.chunkIndex ?? index),
      metadata: item.metadata || {},
      embedding: Array.isArray(item.embedding) ? item.embedding : undefined
    }));
  }

  if (Array.isArray(source) && source.every(item => typeof item === 'string')) {
    return source.map((text, index) => ({
      id: createId(`chunk_${index}`),
      fileId: createId(`inline_${index}`),
      fileName: `inline-${index + 1}.txt`,
      text,
      chunkIndex: index
    }));
  }

  if (Array.isArray(source?.chunks)) {
    return normalizeChunks(source.chunks);
  }

  if (Array.isArray(source?.documents) || typeof source === 'string' || typeof source?.text === 'string') {
    return runChunker(source, { chunkSize: 800, chunkOverlap: 120, keepPageNumber: true }).chunks;
  }

  if (source?.type === 'knowledge-index' && Array.isArray(source?.chunks)) {
    return normalizeChunks(source.chunks);
  }

  return [];
}

function normalizeIndex(source: any): KnowledgeIndex | null {
  if (source?.type === 'knowledge-index' && Array.isArray(source.chunks)) {
    return source as KnowledgeIndex;
  }
  return null;
}

function createChunksFromDocument(document: KnowledgeDocument, chunkSize: number, chunkOverlap: number, keepPageNumber: boolean) {
  const chunks: KnowledgeChunk[] = [];
  let globalIndex = 0;

  const pages = document.pages?.length ? document.pages : [{ pageNumber: 1, text: document.text }];
  pages.forEach(page => {
    const segments = splitText(page.text || '', chunkSize, chunkOverlap);
    segments.forEach(text => {
      chunks.push({
        id: createId(`chunk_${document.fileName}_${globalIndex}`),
        fileId: document.fileId,
        fileName: document.fileName,
        text,
        page: keepPageNumber ? page.pageNumber : undefined,
        chunkIndex: globalIndex,
        metadata: {
          ...(document.metadata || {}),
          page: keepPageNumber ? page.pageNumber : undefined
        }
      });
      globalIndex += 1;
    });
  });

  return chunks;
}

function splitText(text: string, chunkSize: number, chunkOverlap: number) {
  const clean = String(text || '').replace(/\r\n/g, '\n').trim();
  if (!clean) return [];

  const chunks: string[] = [];
  let start = 0;

  while (start < clean.length) {
    const maxEnd = Math.min(clean.length, start + chunkSize);
    let sliceEnd = maxEnd;
    const preview = clean.slice(start, maxEnd);

    if (maxEnd < clean.length) {
      const boundary = Math.max(preview.lastIndexOf('\n'), preview.lastIndexOf(' '));
      if (boundary > chunkSize * 0.5) {
        sliceEnd = start + boundary;
      }
    }

    const segment = clean.slice(start, sliceEnd).trim();
    if (!segment) {
      if (sliceEnd >= clean.length) break;
      start = Math.min(clean.length, maxEnd);
      continue;
    }
    chunks.push(segment);

    if (sliceEnd >= clean.length) break;

    const nextStart = Math.max(start + 1, sliceEnd - chunkOverlap);
    if (nextStart <= start) break;
    start = nextStart;
  }

  return chunks;
}

async function resolveQueryEmbedding(queryInput: any, config: Record<string, any>, index: KnowledgeIndex) {
  if (Array.isArray(queryInput)) {
    return queryInput.map(Number);
  }

  if (Array.isArray(queryInput?.embedding)) {
    return queryInput.embedding.map(Number);
  }

  const query = extractQuery(queryInput, config);
  if (!query) {
    throw new Error('索引检索节点需要 query 文本或 embedding 向量');
  }

  const inheritedConfig = {
    ...(index.embeddingConfig || {}),
    ...getRuntimeEmbeddingConfig(index)
  };
  const mergedConfig = {
    ...inheritedConfig,
    ...config,
    endpoint: config.endpoint || inheritedConfig.endpoint,
    apiKey: config.apiKey || inheritedConfig.apiKey,
    model: config.model || inheritedConfig.model
  };

  const vectors = await requestEmbeddings([query], mergedConfig);
  return vectors[0];
}

function extractQuery(queryInput: any, config: Record<string, any>) {
  if (typeof queryInput === 'string') return queryInput.trim();
  if (typeof queryInput?.query === 'string') return queryInput.query.trim();
  if (typeof queryInput?.text === 'string') return queryInput.text.trim();
  if (typeof config.query === 'string') return config.query.trim();
  return '';
}

function tokenize(text: string) {
  return String(text || '')
    .toLowerCase()
    .split(/[\s,.;:!?()[\]{}"'`，。！？；：、]+/g)
    .map(item => item.trim())
    .filter(Boolean);
}

function cosineSimilarity(a: number[], b: number[]) {
  const len = Math.min(a.length, b.length);
  if (!len) return 0;

  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let index = 0; index < len; index += 1) {
    dot += a[index] * b[index];
    normA += a[index] * a[index];
    normB += b[index] * b[index];
  }

  if (!normA || !normB) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

function isPlainObject(value: any): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function createId(seed: string) {
  return `${seed.replace(/[^a-zA-Z0-9_]/g, '_')}_${Math.random().toString(36).slice(2, 10)}`;
}

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}
