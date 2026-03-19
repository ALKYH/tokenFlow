const TOKENFLOW_API_URL = (import.meta.env.VITE_TOKENFLOW_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const MARKET_LIBRARY_KEY = 'tokenflow.market.installed.v1';
const WORKSPACE_STORAGE_KEY = 'tokenflow.workspace.modules.v1';

type RequestOptions = {
  method?: string;
  body?: unknown;
  token?: string | null;
};

async function tokenflowRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
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
    return localStorage.getItem('SOY_token');
  } catch {
    return '';
  }
}

export async function fetchMarketplacePlugins(params?: { q?: string; category?: string }) {
  const query = new URLSearchParams();
  if (params?.q) query.set('q', params.q);
  if (params?.category) query.set('category', params.category);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return tokenflowRequest<any[]>(`/api/plugins/marketplace${suffix}`);
}

export async function fetchMarketplaceInbox() {
  return tokenflowRequest<any[]>('/api/inbox/messages');
}

export async function fetchRoutingRules() {
  return tokenflowRequest<any[]>('/api/routing/rules');
}

export async function classifyRoutingMessage(payload: {
  category: string;
  channel: string;
  text: string;
  use_ai?: boolean;
  ai_endpoint?: string;
  api_key?: string;
  model?: string;
}) {
  return tokenflowRequest<any>('/api/routing/classify', { method: 'POST', body: payload });
}

export async function installMarketplacePlugin(pluginId: number, token?: string | null) {
  return tokenflowRequest<any>(`/api/plugins/install/${pluginId}`, { method: 'POST', token });
}

export async function fetchMyCloudWorkspaces(token: string) {
  return tokenflowRequest<any[]>('/api/workspaces', { token });
}

export async function saveCloudWorkspace(payload: { name: string; description?: string; file_type?: string; content: Record<string, any> }, token: string) {
  return tokenflowRequest<any>('/api/workspaces', { method: 'POST', body: payload, token });
}

export async function fetchMyProfile(token: string) {
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
  },
  token: string
) {
  return tokenflowRequest<any>('/api/profile/me', { method: 'PATCH', body: payload, token });
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
    return Array.isArray(parsed) ? parsed : [];
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
    kind: next.kind || 'workspace',
    version: next.version || '1.0.0',
    updatedAt: next.updatedAt || new Date().toISOString(),
    stats: {
      nodes: next.stats?.nodes || next.graph?.nodes?.length || 0,
      edges: next.stats?.edges || next.graph?.edges?.length || 0,
      folders: next.stats?.folders || next.graph?.folders?.length || 0
    },
    meta: {
      source: next.meta?.source || 'local',
      tags: next.meta?.tags || []
    },
    graph: {
      nodes: next.graph?.nodes || [],
      edges: next.graph?.edges || [],
      folders: next.graph?.folders || [],
      envVars: next.graph?.envVars || []
    }
  };
}

export function saveWorkspaceSnapshot(snapshot: any) {
  const normalized = normalizeWorkspaceSnapshot(snapshot);
  const next = loadWorkspaceSnapshots().filter((item: any) => item.id !== normalized.id);
  next.unshift(normalized);
  localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(next.slice(0, 24)));
}

export function importPluginToWorkspaceLibrary(plugin: any) {
  saveInstalledMarketPlugin(plugin);
  if (plugin?.workspace_snapshot) {
    saveWorkspaceSnapshot(plugin.workspace_snapshot);
  } else if (plugin?.graph) {
    saveWorkspaceSnapshot(plugin);
  }
}
