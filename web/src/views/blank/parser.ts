import type { Node, Edge } from './editor-core';

// Topological sort (Kahn's algorithm) based on edges (from -> to)
export function topoSort(nodes: Node[], edges: Edge[]): string[] {
  const ids = nodes.map(n => n.id);
  const inDeg = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const id of ids) { inDeg.set(id, 0); adj.set(id, []); }
  for (const e of edges) {
    if (!inDeg.has(e.to.nodeId)) continue;
    inDeg.set(e.to.nodeId, (inDeg.get(e.to.nodeId) || 0) + 1);
    if (!adj.has(e.from.nodeId)) adj.set(e.from.nodeId, []);
    adj.get(e.from.nodeId)!.push(e.to.nodeId);
  }

  const q: string[] = [];
  for (const [id, deg] of inDeg.entries()) {
    if (deg === 0) q.push(id);
  }

  const order: string[] = [];
  while (q.length) {
    const n = q.shift()!;
    order.push(n);
    const neighbors = adj.get(n) || [];
    for (const m of neighbors) {
      inDeg.set(m, (inDeg.get(m) || 0) - 1);
      if (inDeg.get(m) === 0) q.push(m);
    }
  }

  // include any isolated nodes not present in order
  for (const id of ids) {
    if (!order.includes(id)) order.push(id);
  }

  // detect cycle: if some nodes still have in-degree > 0 and were not processed
  const remaining = ids.filter(id => !order.slice(0, ids.length).includes(id));
  // The above ensures all ids are included; to detect true cycle we compare processed count
  if (order.length < ids.length) {
    throw new Error('Cycle detected in graph');
  }

  return order;
}

export function buildDependencyMap(nodes: Node[], edges: Edge[]) {
  const map = new Map<string, string[]>();
  for (const n of nodes) map.set(n.id, []);
  for (const e of edges) {
    if (!map.has(e.to.nodeId)) map.set(e.to.nodeId, []);
    map.get(e.to.nodeId)!.push(e.from.nodeId);
  }
  return map;
}
