import { localStg } from '@/utils/storage';

const TOKENFLOW_API_URL = (import.meta.env.VITE_TOKENFLOW_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const MARKET_LIBRARY_KEY = 'tokenflow.market.installed.v1';
const WORKSPACE_STORAGE_KEY = 'tokenflow.workspace.modules.v1';
const PENDING_WORKSPACE_KEY = 'tokenflow.workspace.pending-import.v1';

type RequestOptions = {
  method?: string;
  body?: unknown;
  token?: string | null;
};

export type WorkspaceSnapshot = ReturnType<typeof normalizeWorkspaceSnapshot>;

async function tokenflowRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = options.token || getStoredAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${TOKENFLOW_API_URL}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}

export function getTokenflowApiUrl() {
  return TOKENFLOW_API_URL;
}

export function getStoredAccessToken() {
  try {
    return localStg.get('token') || '';
  } catch {
    return '';
  }
}

export async function fetchMarketplacePlugins(params?: { q?: string; category?: string; plugin_type?: string }) {
  const query = new URLSearchParams();
  if (params?.q) query.set('q', params.q);
  if (params?.category) query.set('category', params.category);
  if (params?.plugin_type) query.set('plugin_type', params.plugin_type);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return tokenflowRequest<any[]>(`/api/plugins/marketplace${suffix}`);
}

export async function fetchMyPluginLibrary(params?: { plugin_type?: string; library_kind?: string }, token?: string | null) {
  const query = new URLSearchParams();
  if (params?.plugin_type) query.set('plugin_type', params.plugin_type);
  if (params?.library_kind) query.set('library_kind', params.library_kind);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return tokenflowRequest<any[]>(`/api/plugins/library${suffix}`, { token });
}

export async function uploadPlugin(payload: Record<string, any>, token?: string | null) {
  return tokenflowRequest<any>('/api/plugins/upload', { method: 'POST', body: payload, token });
}

export async function fetchMarketplaceInbox(params?: { channel?: string; category?: string }) {
  const query = new URLSearchParams();
  if (params?.channel) query.set('channel', params.channel);
  if (params?.category) query.set('category', params.category);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return tokenflowRequest<any[]>(`/api/inbox/messages${suffix}`);
}

export async function fetchInboxChannels(token?: string | null) {
  return tokenflowRequest<any[]>('/api/inbox/channels', { token });
}

export async function createInboxMessage(payload: Record<string, any>, token?: string | null, ingest = false) {
  return tokenflowRequest<any>(ingest ? '/api/inbox/ingest' : '/api/inbox/messages', {
    method: 'POST',
    body: payload,
    token
  });
}

export async function markInboxMessagesRead(ids: number[], is_read = true, token?: string | null) {
  return tokenflowRequest<any[]>('/api/inbox/messages/read', {
    method: 'PATCH',
    body: { ids, is_read },
    token
  });
}

export async function fetchRoutingRules(token?: string | null) {
  return tokenflowRequest<any[]>('/api/routing/rules', { token });
}

export async function fetchRoutingSummary(token?: string | null) {
  return tokenflowRequest<any>('/api/routing/summary', { token });
}

export async function saveRoutingRule(payload: Record<string, any>, token?: string | null) {
  return tokenflowRequest<any>('/api/routing/rules', { method: 'POST', body: payload, token });
}

export async function updateRoutingRule(ruleId: number, payload: Record<string, any>, token?: string | null) {
  return tokenflowRequest<any>(`/api/routing/rules/${ruleId}`, { method: 'PATCH', body: payload, token });
}

export async function classifyRoutingMessage(payload: {
  category?: string;
  channel?: string;
  text: string;
  use_ai?: boolean;
  ai_endpoint?: string;
  api_key?: string;
  model?: string;
  api_name?: string;
  file_name?: string;
  file_type?: string;
}) {
  return tokenflowRequest<any>('/api/routing/classify', { method: 'POST', body: payload });
}

export async function installMarketplacePlugin(pluginId: number, token?: string | null) {
  return tokenflowRequest<any>(`/api/plugins/install/${pluginId}`, { method: 'POST', token });
}

export async function fetchMyCloudWorkspaces(token?: string | null, fileType?: string, q?: string) {
  const query = new URLSearchParams();
  if (fileType) query.set('file_type', fileType);
  if (q) query.set('q', q);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return tokenflowRequest<any[]>(`/api/workspaces${suffix}`, { token });
}

export async function fetchWorkspaceById(workspaceId: number, token?: string | null) {
  return tokenflowRequest<any>(`/api/workspaces/${workspaceId}`, { token });
}

export async function saveCloudWorkspace(
  payload: { id?: number; name: string; description?: string; file_type?: string; content: Record<string, any> },
  token?: string | null
) {
  return tokenflowRequest<any>('/api/workspaces', { method: 'POST', body: payload, token });
}

export async function deleteCloudWorkspace(workspaceId: number, token?: string | null) {
  return tokenflowRequest<{ deleted: boolean; id: number }>(`/api/workspaces/${workspaceId}`, { method: 'DELETE', token });
}

export async function fetchMyProfile(token?: string | null) {
  return tokenflowRequest<any>('/api/profile/me', { token });
}

export async function updateMyProfile(
  payload: {
    display_name: string
    bio?: string
    avatar_url?: string
    preferences?: Record<string, any>
    api_provider?: string
    api_key?: string
    api_keys?: Array<{
      provider: string
      secret_name: string
      request_prefix?: string
      priority?: number
      api_key?: string
      is_active?: boolean
    }>
  },
  token?: string | null
) {
  return tokenflowRequest<any>('/api/profile/me', { method: 'PATCH', body: payload, token });
}

export async function resolveRoutingContext(
  payload: {
    category?: string
    channel?: string
    api_name?: string
    file_name?: string
    file_type?: string
  },
  token?: string | null
) {
  return tokenflowRequest<any>('/api/routing/resolve', { method: 'POST', body: payload, token });
}

export async function publishWorkspacePlugin(
  payload: {
    workspace_id?: number
    name: string
    slug: string
    summary?: string
    category?: string
    plugin_type?: string
    icon?: string
    tags?: string[]
    request_api_name?: string
    file_type?: string
    is_public?: boolean
    library_kind?: string
  },
  token?: string | null
) {
  return tokenflowRequest<any>('/api/plugins/publish-workspace', { method: 'POST', body: payload, token });
}

export function loadInstalledMarketLibrary() {
  try {
    const raw = localStorage.getItem(MARKET_LIBRARY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveInstalledMarketPlugin(plugin: any) {
  const current = loadInstalledMarketLibrary().filter((item: any) => item.slug !== plugin.slug);
  current.unshift(plugin);
  localStorage.setItem(MARKET_LIBRARY_KEY, JSON.stringify(current.slice(0, 48)));
}

export function loadWorkspaceSnapshots() {
  try {
    const raw = localStorage.getItem(WORKSPACE_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map(item => normalizeWorkspaceSnapshot(item)) : [];
  } catch {
    return [];
  }
}

export function normalizeWorkspaceSnapshot(snapshot: any) {
  const next = snapshot || {};
  return {
    id: next.id || `workspace_${Date.now()}`,
    name: next.name || 'Untitled Workspace',
    description: next.description || '',
    kind: next.kind || next.file_type || 'workspace',
    version: next.version || '1.0.0',
    updatedAt: next.updatedAt || next.updated_at || new Date().toISOString(),
    stats: {
      nodes: next.stats?.nodes || next.graph?.nodes?.length || next.content?.graph?.nodes?.length || 0,
      edges: next.stats?.edges || next.graph?.edges?.length || next.content?.graph?.edges?.length || 0,
      folders: next.stats?.folders || next.graph?.folders?.length || next.content?.graph?.folders?.length || 0
    },
    meta: {
      source: next.meta?.source || next.library_kind || next.source?.channel || 'local',
      tags: next.meta?.tags || next.tags || []
    },
    graph: {
      nodes: next.graph?.nodes || next.content?.graph?.nodes || [],
      edges: next.graph?.edges || next.content?.graph?.edges || [],
      folders: next.graph?.folders || next.content?.graph?.folders || [],
      envVars: next.graph?.envVars || next.content?.graph?.envVars || []
    }
  };
}

export function saveWorkspaceSnapshot(snapshot: any) {
  const normalized = normalizeWorkspaceSnapshot(snapshot);
  const next = loadWorkspaceSnapshots().filter((item: any) => item.id !== normalized.id);
  next.unshift(normalized);
  localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(next.slice(0, 24)));
  return normalized;
}

export function savePendingWorkspaceImport(snapshot: any) {
  const normalized = normalizeWorkspaceSnapshot(snapshot);
  localStorage.setItem(PENDING_WORKSPACE_KEY, JSON.stringify(normalized));
  return normalized;
}

export function consumePendingWorkspaceImport() {
  try {
    const raw = localStorage.getItem(PENDING_WORKSPACE_KEY);
    if (!raw) return null;
    localStorage.removeItem(PENDING_WORKSPACE_KEY);
    return normalizeWorkspaceSnapshot(JSON.parse(raw));
  } catch {
    return null;
  }
}

export async function parseWorkspaceFile(file: File) {
  const text = await file.text();
  const parsed = JSON.parse(text);
  return normalizeWorkspaceSnapshot(parsed);
}

export function importPluginToWorkspaceLibrary(plugin: any) {
  saveInstalledMarketPlugin(plugin);
  if (plugin?.workspace_snapshot) {
    saveWorkspaceSnapshot(plugin.workspace_snapshot);
  } else if (plugin?.graph) {
    saveWorkspaceSnapshot(plugin);
  }
}
