export type Node = {
  id: string;
  x: number;
  y: number;
  label: string;
  category?: string;
  inputs?: string[];
  outputs?: string[];
  inputTypes?: string[];
  outputTypes?: string[];
  code?: string;
  lastResult?: any;
  isInit?: boolean;
  isOutput?: boolean;
  color?: string;
  status?: 'idle' | 'running' | 'error' | 'done' | 'disabled';
  meta?: Record<string, any>;
  resources?: Array<{
    id: string;
    name: string;
    kind?: string;
    file?: File;
    size?: number;
    lastModified?: number;
  }>;
};
export type Edge = { id: string; from: { nodeId: string; portIndex: number }; to: { nodeId: string; portIndex: number } };

export const NODE_W = 160;
export const headerHeight = 32;
export const rowHeight = 28;
export const rowGap = 6; // gap between rows in .node-body flex column
export const BODY_PADDING = 8;
export const PORT_X_OFFSET = 20;

export function computePortCenter(n: Node, type: 'in' | 'out', index: number) {
  const nx = n.x;
  const ny = n.y;
  if (type === 'in') {
    const cx = nx + PORT_X_OFFSET;
    const cy = ny + headerHeight + BODY_PADDING + index * (rowHeight + rowGap) + rowHeight / 2;
    return { cx, cy };
  }
  // out
  const inCount = n.inputs ? n.inputs.length : 0;
  const rowIndex = inCount + index;
  const cx = nx + NODE_W - PORT_X_OFFSET;
  const cy = ny + headerHeight + BODY_PADDING + rowIndex * (rowHeight + rowGap) + rowHeight / 2;
  return { cx, cy };
}

export function findPortAt(nodes: Node[], x: number, y: number, radius = 14) {
  for (const n of nodes) {
    if (n.inputs) {
      for (let i = 0; i < n.inputs.length; i++) {
        const { cx, cy } = computePortCenter(n, 'in', i);
        if (Math.hypot(x - cx, y - cy) < radius) return { nodeId: n.id, type: 'in' as const, index: i };
      }
    }
    if (n.outputs) {
      for (let i = 0; i < n.outputs.length; i++) {
        const { cx, cy } = computePortCenter(n, 'out', i);
        if (Math.hypot(x - cx, y - cy) < radius) return { nodeId: n.id, type: 'out' as const, index: i };
      }
    }
  }
  return null;
}

export function edgePoints(edge: Edge, nodes: Node[]) {
  const fromNode = nodes.find(n => n.id === edge.from.nodeId)!;
  const toNode = nodes.find(n => n.id === edge.to.nodeId)!;
  const fromCenter = computePortCenter(fromNode, 'out', edge.from.portIndex);
  const toCenter = computePortCenter(toNode, 'in', edge.to.portIndex);
  return { x1: fromCenter.cx, y1: fromCenter.cy, x2: toCenter.cx, y2: toCenter.cy };
}

export function edgePathFromPoints(x1: number, y1: number, x2: number, y2: number) {
  const dx = x2 - x1;
  const cpx = Math.max(40, Math.abs(dx) / 2);
  let cp1x: number, cp2x: number;
  if (dx >= 0) {
    cp1x = x1 + cpx;
    cp2x = x2 - cpx;
  } else {
    cp1x = x1 - cpx;
    cp2x = x2 + cpx;
  }
  return `M ${x1} ${y1} C ${cp1x} ${y1} ${cp2x} ${y2} ${x2} ${y2}`;
}

export function edgePath(edge: Edge, nodes: Node[]) {
  const p = edgePoints(edge, nodes);
  return edgePathFromPoints(p.x1, p.y1, p.x2, p.y2);
}

export function tempEdgePathFrom(temp: { x1: number; y1: number; x2: number; y2: number } | null) {
  if (!temp) return '';
  return edgePathFromPoints(temp.x1, temp.y1, temp.x2, temp.y2);
}
