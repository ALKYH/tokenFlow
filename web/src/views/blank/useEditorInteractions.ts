import { Ref } from 'vue';
import { findPortAt, tempEdgePathFrom, computePortCenter, NODE_W, headerHeight, rowHeight, BODY_PADDING, rowGap } from './editor-core';
import type { Node as NodeType, Edge as EdgeType } from './editor-core';

export interface UseEditorParams {
  areaRef: Ref<HTMLElement | null>;
  nodes: NodeType[];
  edges: EdgeType[];
  selectedIds: Ref<string[]>;
  dragging: any;
  viewScale: Ref<number>;
  viewOffset: { x: number; y: number };
  marquee: Ref<{ visible: boolean; x: number; y: number; w: number; h: number }>;
  marqueeHits: Ref<string[]>;
  marqueeStart: { x: number; y: number; shift: boolean };
  edgeStart: Ref<any>;
  tempEdge: Ref<any>;
  hoverPort: Ref<any>;
  folders: any[];
  panMode: Ref<boolean>;
  isPanning: Ref<boolean>;
  panStart: { x: number; y: number; offsetX: number; offsetY: number };
  debugLogs: string[];
}

export default function useEditorInteractions(params: UseEditorParams) {
  const {
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
  } = params;

  function logDebug(...args: any[]) {
    try {
      const msg = args.map(a => (typeof a === 'string' ? a : JSON.stringify(a))).join(' ');
      debugLogs.unshift(`${new Date().toISOString()} ${msg}`);
      if (debugLogs.length > 120) debugLogs.pop();
    } catch (e) {}
  }

  // state for middle-button long-press panning
  const middlePress: { timer: any; active: boolean; prevPan: boolean; pointerId: number } = { timer: null, active: false, prevPan: false, pointerId: -1 };

  function handleNodePointerDown(e: PointerEvent, node: NodeType) {
    if (panMode.value) return;
    if ((e as PointerEvent).shiftKey) {
      const idx = selectedIds.value.indexOf(node.id);
      if (idx >= 0) selectedIds.value.splice(idx, 1);
      else selectedIds.value.push(node.id);
    } else {
      selectedIds.value = [node.id];
    }
    const target = e.currentTarget as HTMLElement | null;
    if (target) target.setPointerCapture(e.pointerId);
    dragging.node = node;
    dragging.multi = false;
    dragging.offsets = {};
    const area = areaRef.value;
    if (area) {
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      dragging.offsetX = worldX - node.x;
      dragging.offsetY = worldY - node.y;
      if (selectedIds.value.length > 1 && selectedIds.value.includes(node.id)) {
        dragging.multi = true;
        for (const id of selectedIds.value) {
          const n = nodes.find(x => x.id === id);
          if (!n) continue;
          dragging.offsets[id] = { offsetX: worldX - n.x, offsetY: worldY - n.y };
        }
      }
    } else {
      dragging.offsetX = e.offsetX;
      dragging.offsetY = e.offsetY;
    }
    window.addEventListener('pointermove', handlePointerMoveWindow);
    window.addEventListener('pointerup', handlePointerUpWindow);
  }

  function handleFolderPointerDown(e: PointerEvent, folder: any) {
    if (panMode.value) return;
    const target = e.currentTarget as HTMLElement | null;
    try {
      if (target && typeof e.pointerId === 'number') {
        try { target.setPointerCapture(e.pointerId); } catch (err) { /* ignore capture errors */ }
      }
    } catch (err) {}
    dragging.folder = folder;
    dragging.multi = false;
    const area = areaRef.value;
    if (area) {
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      dragging.offsetX = worldX - folder.x;
      dragging.offsetY = worldY - folder.y;
    } else {
      dragging.offsetX = e.offsetX;
      dragging.offsetY = e.offsetY;
    }
    logDebug('startFolderDrag', { id: folder.id, offsetX: dragging.offsetX, offsetY: dragging.offsetY });
    window.addEventListener('pointermove', handlePointerMoveWindow);
    window.addEventListener('pointerup', handlePointerUpWindow);
  }

  function handlePointerMoveWindow(e: PointerEvent) {
    // marquee live update
    if (marquee.value.visible && !dragging.node && !edgeStart.value && !isPanning.value) {
      const area = areaRef.value!.getBoundingClientRect();
      const worldX = (e.clientX - area.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - area.top - viewOffset.y) / viewScale.value;
      const x = Math.min(marqueeStart.x, worldX);
      const y = Math.min(marqueeStart.y, worldY);
      const w = Math.abs(worldX - marqueeStart.x);
      const h = Math.abs(worldY - marqueeStart.y);
      marquee.value.x = x; marquee.value.y = y; marquee.value.w = w; marquee.value.h = h;
      const hits: string[] = [];
      for (const n of nodes) {
        const rows = Math.max((n.inputs?.length || 0) + (n.outputs?.length || 0), 1);
        const nh = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
        const cx = n.x + NODE_W / 2;
        const cy = n.y + nh / 2;
        if (cx >= x && cx <= x + w && cy >= y && cy <= y + h) hits.push(n.id);
      }
      marqueeHits.value = hits;
      return;
    }

    if (dragging.multi) {
      const area = areaRef.value!;
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      for (const id of selectedIds.value) {
        const n = nodes.find(x => x.id === id);
        if (!n) continue;
        const off = dragging.offsets[id];
        if (!off) continue;
        const nx = worldX - off.offsetX;
        const ny = worldY - off.offsetY;
        const maxX = Math.max(0, rect.width / viewScale.value - NODE_W);
        const rows = Math.max((n.inputs?.length || 0) + (n.outputs?.length || 0), 1);
        const nodeH = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
        const maxY = Math.max(0, rect.height / viewScale.value - nodeH);
        n.x = Math.max(0, Math.min(maxX, nx));
        n.y = Math.max(0, Math.min(maxY, ny));
      }
    } else if (dragging.node) {
      const area = areaRef.value!;
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      const nx = worldX - dragging.offsetX;
      const ny = worldY - dragging.offsetY;
      const maxX = Math.max(0, rect.width / viewScale.value - NODE_W);
      const rows = Math.max((dragging.node.inputs?.length || 0) + (dragging.node.outputs?.length || 0), 1);
      const nodeH = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
      const maxY = Math.max(0, rect.height / viewScale.value - nodeH);
      dragging.node.x = Math.max(0, Math.min(maxX, nx));
      dragging.node.y = Math.max(0, Math.min(maxY, ny));

      // indicate folders when node is dragged over them
      try {
        const cx = dragging.node.x + NODE_W / 2;
        const rows = Math.max((dragging.node.inputs?.length || 0) + (dragging.node.outputs?.length || 0), 1);
        const nodeH = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
        const cy = dragging.node.y + nodeH / 2;
        for (const f of folders) {
          if (!f) continue;
          const inside = cx >= f.x && cx <= f.x + f.w && cy >= f.y && cy <= f.y + f.h;
          f._hover = !!inside;
        }
      } catch (e) {}
    } else if (isPanning.value) {
      viewOffset.x = panStart.offsetX + (e.clientX - panStart.x);
      viewOffset.y = panStart.offsetY + (e.clientY - panStart.y);
    } else if (dragging.folder) {
      const area = areaRef.value!;
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      const nx = worldX - dragging.offsetX;
      const ny = worldY - dragging.offsetY;
      const dx = nx - dragging.folder.x;
      const dy = ny - dragging.folder.y;
      dragging.folder.x = nx;
      dragging.folder.y = ny;
      // move child nodes together
      try {
        for (const id of dragging.folder.children || []) {
          const n = nodes.find(x => x.id === id);
          if (!n) continue;
          n.x = n.x + dx;
          n.y = n.y + dy;
        }
      } catch (e) {}
      try { logDebug('movingFolder', { id: dragging.folder.id, x: dragging.folder.x, y: dragging.folder.y }); } catch (e) {}
    } else if (edgeStart.value) {
      const area = areaRef.value!.getBoundingClientRect();
      const x2 = (e.clientX - area.left - viewOffset.x) / viewScale.value;
      const y2 = (e.clientY - area.top - viewOffset.y) / viewScale.value;
      tempEdge.value = { x1: edgeStart.value.x, y1: edgeStart.value.y, x2, y2 };
      logDebug('tempEdge update', tempEdge.value);
      const hit = findPortAt(nodes, x2, y2);
      if (hit) {
        // check whether the hovered input port already has an incoming edge
        let invalid = false;
        try {
          if (hit.type === 'in') {
            // if any existing edge targets this node/input port, mark invalid
            invalid = edges.some(e => e.to.nodeId === hit.nodeId && e.to.portIndex === hit.index);
          }
        } catch (e) { invalid = false }
        hoverPort.value = { nodeId: hit.nodeId, type: hit.type, index: hit.index, invalid };
        logDebug('hoverPort', hoverPort.value);
      } else {
        hoverPort.value = null;
      }
    }
  }

  function handlePointerUpWindow(e: PointerEvent) {
    window.removeEventListener('pointermove', handlePointerMoveWindow);
    window.removeEventListener('pointerup', handlePointerUpWindow);

    // cancel pending middle-press timer if any
    try {
      if ((middlePress as any).timer) { clearTimeout((middlePress as any).timer); (middlePress as any).timer = null; }
    } catch (e) {}

    // if middle-press had activated temporary pan mode, restore previous panMode immediately
    try {
      if ((middlePress as any).active) {
        (middlePress as any).active = false;
        panMode.value = !!(middlePress as any).prevPan;
        isPanning.value = false;
      }
    } catch (e) {}

    if (dragging.node) {
      // when node drag ends, check if it is dropped into any folder
      try {
        const area = areaRef.value!;
        const rect = area.getBoundingClientRect();
        const cx = dragging.node.x + NODE_W / 2;
        const cy = dragging.node.y + headerHeight + BODY_PADDING + 10; // approximate center
        // assign to first folder that contains center
        for (const f of folders) {
          const inside = cx >= f.x && cx <= f.x + f.w && cy >= f.y && cy <= f.y + f.h;
          if (inside) {
            f.children = f.children || [];
            if (!f.children.includes(dragging.node.id)) f.children.push(dragging.node.id);
            f._hover = false;
          } else {
            // remove from folder if moved out
            if (f.children) {
              const idx = f.children.indexOf(dragging.node.id);
              if (idx >= 0) f.children.splice(idx, 1);
            }
            f._hover = false;
          }
        }
      } catch (e) {}
      dragging.node = null;
      dragging.multi = false;
      dragging.offsets = {};
      return;
    }
    if (dragging.multi) {
      dragging.multi = false;
      dragging.offsets = {};
      return;
    }

    if (isPanning.value) {
      isPanning.value = false;
      return;
    }

    if (edgeStart.value) {
      try { if (edgeStart.value.pointerId != null && edgeStart.value.pointerId !== undefined) {
        // release capture if any
        // we don't have the captured element reference here; callers release if needed
      } } catch (err) {}

      const rect = areaRef.value!.getBoundingClientRect();
      const x = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const y = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      const hitPort = findPortAt(nodes, x, y);

      // track whether we actually created a new edge during this pointerup
      let created = false;

      if (hitPort) {
        if (hitPort.nodeId === edgeStart.value.nodeId) {
          logDebug('prevent self-connection', { nodeId: hitPort.nodeId });
        } else if (edgeStart.value.type === 'out' && hitPort.type === 'in') {
          // prevent connecting to an input that already has an incoming edge
          const occupied = edges.some(e => e.to.nodeId === hitPort.nodeId && e.to.portIndex === hitPort.index);
          if (occupied) {
            logDebug('blocked connection: target input already occupied', { target: hitPort });
          } else {
            edges.push({ id: `edge_${edges.length + 1}`, from: { nodeId: edgeStart.value.nodeId, portIndex: edgeStart.value.portIndex }, to: { nodeId: hitPort.nodeId, portIndex: hitPort.index } });
            logDebug('edge created', edges[edges.length-1]);
            created = true;
          }
        } else if (edgeStart.value.type === 'in' && hitPort.type === 'out') {
          // connecting an input-start to an output-end is allowed (output can have many connections)
          edges.push({ id: `edge_${edges.length + 1}`, from: { nodeId: hitPort.nodeId, portIndex: hitPort.index }, to: { nodeId: edgeStart.value.nodeId, portIndex: edgeStart.value.portIndex } });
          logDebug('edge created', edges[edges.length-1]);
          created = true;
        }
      }

      // note: if the user started drag from an input and removed an existing edge,
      // do NOT restore it on cancelled redirects — the user's action deletes the connection.

      edgeStart.value = null;
      tempEdge.value = null;
      hoverPort.value = null;
    }

    // finalize marquee selection
    if (marquee.value.visible) {
      const rect = marquee.value;
      const selected = nodes.filter(n => {
        const rows = Math.max((n.inputs?.length || 0) + (n.outputs?.length || 0), 1);
        const h = headerHeight + BODY_PADDING * 2 + rows * rowHeight + Math.max(0, rows - 1) * rowGap;
        const cx = n.x + NODE_W / 2;
        const cy = n.y + h / 2;
        return cx >= rect.x && cx <= rect.x + rect.w && cy >= rect.y && cy <= rect.y + rect.h;
      }).map(n => n.id);
      if (marqueeStart.shift) {
        for (const id of selected) if (!selectedIds.value.includes(id)) selectedIds.value.push(id);
      } else {
        selectedIds.value = selected;
      }
      marquee.value.visible = false;
    }

    // finalize folder drag if any
    try {
      if (dragging.folder) {
        // release any pointer capture on the area if present
        try {
          const area = areaRef.value;
          if (area && typeof e.pointerId === 'number') {
            try { area.releasePointerCapture(e.pointerId); } catch (er) {}
          }
        } catch (er) {}
        dragging.folder = null;
        dragging.offsetX = 0; dragging.offsetY = 0;
      }
    } catch (er) {}
  }

  function handleStartEdge(ev: PointerEvent, node: NodeType, type: 'in' | 'out', portIndex: number) {
    if (panMode.value) return;
    const center = computePortCenter(node, type, portIndex);
    const cx = center.cx; const cy = center.cy;
    const el = ev.currentTarget as HTMLElement | null;
    try { if (el && typeof ev.pointerId === 'number') { el.setPointerCapture(ev.pointerId); } } catch (e) {}
    edgeStart.value = { nodeId: node.id, type, portIndex, x: cx, y: cy, pointerId: ev.pointerId };
    // If starting drag from an input port that already has an incoming edge, remove it now
    if (type === 'in') {
      try {
        const idx = edges.findIndex(e => e.to.nodeId === node.id && e.to.portIndex === portIndex);
        if (idx >= 0) {
          const removed = edges.splice(idx, 1)[0];
          // save removed edge on the edgeStart so we can restore it if the redirect is cancelled
          edgeStart.value.removedEdge = removed;
          logDebug('removed existing edge for redirect', removed);
        }
      } catch (e) {}
    }
    tempEdge.value = { x1: cx, y1: cy, x2: cx, y2: cy };
    logDebug('startEdge', { node: node.id, type, portIndex, x: cx, y: cy, pointerId: ev.pointerId });
    window.addEventListener('pointermove', handlePointerMoveWindow);
    window.addEventListener('pointerup', handlePointerUpWindow);
  }

  function handlePointerDownArea(e: PointerEvent) {
    const area = areaRef.value;
    if (!area) return;
    // if click is inside a node or folder, don't treat it as background click
    try {
      const tgt = e.target as Element | null;
      if (tgt) {
        if (tgt.closest && (tgt.closest('.node') || tgt.closest('.folder'))) {
          return;
        }
      }
    } catch (er) {}
    // middle button long-press to enable pan (drag) mode
    if (e.button === 1) {
      try { e.preventDefault(); } catch (er) {}
      // start long-press timer
      (middlePress as any).prevPan = panMode.value;
      (middlePress as any).pointerId = (e as PointerEvent).pointerId;
      if ((middlePress as any).timer) clearTimeout((middlePress as any).timer);
      (middlePress as any).timer = setTimeout(() => {
        (middlePress as any).timer = null;
        (middlePress as any).active = true;
        panMode.value = true;
        isPanning.value = true;
        panStart.x = (e as PointerEvent).clientX; panStart.y = (e as PointerEvent).clientY; panStart.offsetX = viewOffset.x; panStart.offsetY = viewOffset.y;
        window.addEventListener('pointermove', handlePointerMoveWindow);
        window.addEventListener('pointerup', handlePointerUpWindow);
      }, 50);
      try { const tgt = e.currentTarget as HTMLElement | null; if (tgt && typeof e.pointerId === 'number') tgt.setPointerCapture(e.pointerId); } catch (er) {}
      return;
    }

    if (panMode.value && e.button === 0) {
      isPanning.value = true;
      panStart.x = e.clientX; panStart.y = e.clientY; panStart.offsetX = viewOffset.x; panStart.offsetY = viewOffset.y;
      window.addEventListener('pointermove', handlePointerMoveWindow);
      window.addEventListener('pointerup', handlePointerUpWindow);
      return;
    }
    if (e.button === 0) {
      const rect = area.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - viewOffset.x) / viewScale.value;
      const worldY = (e.clientY - rect.top - viewOffset.y) / viewScale.value;
      marqueeStart.x = worldX; marqueeStart.y = worldY; marqueeStart.shift = e.shiftKey;
      marquee.value.visible = true; marquee.value.x = worldX; marquee.value.y = worldY; marquee.value.w = 0; marquee.value.h = 0;
      window.addEventListener('pointermove', handlePointerMoveWindow);
      window.addEventListener('pointerup', handlePointerUpWindow);
      return;
    }
    if (edgeStart.value) {
      edgeStart.value = null; tempEdge.value = null;
    }
    selectedIds.value = [];
  }

  function getTempEdgePath() {
    return tempEdgePathFrom(tempEdge.value);
  }

  function handleWheel(e: WheelEvent) {
    const area = areaRef.value;
    if (!area) return;
    e.preventDefault();
    const rect = area.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const beforeX = (cx - viewOffset.x) / viewScale.value;
    const beforeY = (cy - viewOffset.y) / viewScale.value;
    const scaleFactor = Math.pow(1.0015, -e.deltaY);
    const newScale = Math.max(0.4, Math.min(3, viewScale.value * scaleFactor));
    viewScale.value = newScale;
    viewOffset.x = cx - beforeX * newScale;
    viewOffset.y = cy - beforeY * newScale;
    // clamp offsets to avoid extreme translations that may cause page overflow/scrollbars
    try {
      const maxPanX = rect.width * Math.max(1, newScale) * 1.2;
      const maxPanY = rect.height * Math.max(1, newScale) * 1.2;
      viewOffset.x = Math.max(-maxPanX, Math.min(maxPanX, viewOffset.x));
      viewOffset.y = Math.max(-maxPanY, Math.min(maxPanY, viewOffset.y));
    } catch (e) {}
  }

  return {
    handleNodePointerDown,
    handlePointerMoveWindow,
    handlePointerUpWindow,
    handlePointerDownArea,
    handleStartEdge,
    getTempEdgePath,
    handleFolderPointerDown,
    handleWheel
  };
}
