import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Graph } from '@antv/g6'
import {
  Minus,
  Plus,
  Maximize,
  Maximize2,
  RotateCcw,
  RefreshCw,
  Search,
  Network,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EmptyState } from '@/components/common/EmptyState'
import { GraphLegend, GraphRealtimeHint } from '@/components/graph/GraphOverlays'
import { GraphDetailShell } from '@/components/graph/GraphDetailShell'
import { EdgeDetail, NodeDetail } from '@/components/graph/GraphDetailContent'
import { buildGraphView, type GraphViewEdge } from '@/lib/graph-view'
import type { GraphData, GraphNode } from '@/lib/graph-types'

type LayoutKind = 'd3-force' | 'radial' | 'concentric' | 'antv-dagre'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any

const LAYOUTS: Record<LayoutKind, Any> = {
  'd3-force': {
    type: 'd3-force',
    collide: { radius: 28 },
    link: { distance: 80 },
    manyBody: { strength: -160 },
  },
  radial: { type: 'radial', unitRadius: 110, linkDistance: 120 },
  concentric: { type: 'concentric', nodeSize: 28 },
  'antv-dagre': { type: 'antv-dagre', rankdir: 'LR', nodesep: 20, ranksep: 60 },
}

type Selection = { type: 'node' | 'edge'; id: string }
type Selected =
  | { kind: 'node'; data: GraphNode; type: string; color: string }
  | { kind: 'edge'; edge: GraphViewEdge }
  | null

interface GraphPanelG6Props {
  graphData: GraphData | null
  loading?: boolean
  currentPhase?: number
  isSimulating?: boolean
  onRefresh?: () => void
  onToggleMaximize?: () => void
  /** 父级布局/视图变化的信号；变化时主动 resize + 重新适配（不依赖 ResizeObserver 时序）。 */
  resizeKey?: string | number
}

/** 监听 <html> 上的 dark 类，返回当前是否暗色（与 stores/theme 一致）。 */
function useDarkMode(): boolean {
  const [dark, setDark] = useState(
    () => typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
  )
  useEffect(() => {
    const el = document.documentElement
    const obs = new MutationObserver(() => setDark(el.classList.contains('dark')))
    obs.observe(el, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return dark
}

/** 读取全局主题 CSS 变量（形如 "243 75% 58%"）并解析为 HSL 分量；读不到时回退。 */
function readHsl(name: string, fallback: [number, number, number]): [number, number, number] {
  if (typeof document === 'undefined') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!raw) return fallback
  const parts = raw.split('/')[0].trim().split(/\s+/)
  const h = parseFloat(parts[0])
  const s = parseFloat(parts[1])
  const l = parseFloat(parts[2])
  return [h, s, l].some(Number.isNaN) ? fallback : [h, s, l]
}

function hsl([h, s, l]: [number, number, number], a = 1): string {
  return a >= 1 ? `hsl(${h}, ${s}%, ${l}%)` : `hsla(${h}, ${s}%, ${l}%, ${a})`
}

/**
 * 从全局设计 token 解析图谱所需颜色，保证 G6 画布与「玻璃 + 单一 indigo 强调」主题一致：
 * 画布底/标签取 --background/--foreground；选中/关联高亮统一收敛到 --primary（indigo），
 * 关联态用提亮一档的浅 indigo 与选中态区分（同色相，不再用离题的橙/青）。
 */
function useGraphTheme(dark: boolean) {
  return useMemo(() => {
    const bg = readHsl('--background', dark ? [222.2, 84, 4.9] : [0, 0, 100])
    const fg = readHsl('--foreground', dark ? [210, 40, 98] : [222.2, 84, 4.9])
    const pri = readHsl('--primary', dark ? [239, 84, 67] : [243, 75, 58])
    const accentSoft: [number, number, number] = [pri[0], Math.max(pri[1] - 8, 0), Math.min(pri[2] + 14, 90)]
    return {
      canvasBg: hsl(bg),
      labelFill: hsl(fg),
      accent: hsl(pri), // 选中态：强调 indigo
      accentSoft: hsl(accentSoft), // 关联态：浅一档 indigo
    }
    // dark 切换时 <html> 已带上 .dark，重算即可读到对应模式的 token
  }, [dark])
}

/** 知识图谱可视化面板（@antv/g6 引擎，移植自 kg-gen，适配 SuperFish 数据模型）。 */
export function GraphPanelG6({
  graphData,
  loading,
  currentPhase,
  isSimulating,
  onRefresh,
  onToggleMaximize,
  resizeKey,
}: GraphPanelG6Props) {
  const { t } = useTranslation()
  const dark = useDarkMode()

  const wrapRef = useRef<HTMLDivElement>(null)
  const miniRef = useRef<HTMLCanvasElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const collapsedRef = useRef<Set<string>>(new Set())
  const activeEdgesRef = useRef<string[]>([])

  const [selections, setSelections] = useState<Selection[]>([])
  const [selected, setSelected] = useState<Selected>(null)
  const [expandedLoops, setExpandedLoops] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [layout, setLayout] = useState<LayoutKind>('d3-force')
  const [hideIsolated, setHideIsolated] = useState(true)

  const selectionsRef = useRef(selections)
  const applySelRef = useRef<() => void>(() => {})
  selectionsRef.current = selections

  const view = useMemo(() => buildGraphView(graphData), [graphData])
  const hasData = view.nodes.length > 0

  const theme = useGraphTheme(dark)
  const { canvasBg, labelFill } = theme

  // 实体类型 → 颜色（图例用）
  const typeColors = useMemo(() => {
    const map = new Map<string, string>()
    view.clusters.forEach((c) => map.set(c.id, c.color))
    return map
  }, [view])

  // 选中项/详情联动
  const toggleSelection = (sel: Selection, detail: Selected) => {
    setSelected(detail)
    setSelections((prev) => {
      const exists = prev.find((s) => s.type === sel.type && s.id === sel.id)
      return exists ? prev.filter((s) => s !== exists) : [...prev, sel]
    })
  }
  const clearSelections = () => {
    setSelections([])
    setSelected(null)
  }

  // 切换详情时收起所有自环展开项（与 d3 版 GraphPanel 行为一致）
  useEffect(() => {
    setExpandedLoops(new Set())
  }, [selected])

  const toggleLoop = (id: string) =>
    setExpandedLoops((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const data = useMemo(() => {
    const isolated = new Set(view.isolatedEntities)
    const nodes = view.nodes
      .filter((n) => !(hideIsolated && isolated.has(n.id)))
      .map((n) => ({
        id: n.id,
        data: {
          label: n.label,
          cluster: n.cluster,
          color: n.color,
          size: Math.max(18, n.radius),
          degree: n.degree,
        },
      }))
    const visible = new Set(nodes.map((n) => n.id))
    const edges = view.edges
      .filter((e) => visible.has(e.source) && visible.has(e.target))
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        data: {
          color: e.color,
          predicate: e.predicate,
          sourceLabel: e.sourceLabel,
          targetLabel: e.targetLabel,
        },
      }))
    return { nodes, edges }
  }, [view, hideIsolated])

  useEffect(() => {
    const container = wrapRef.current
    if (!container || !hasData) return

    // 规模自适应：大图自动降级特效（阴影/气泡/动画/粒子流），避免卡顿
    const count = data.nodes.length
    const isLarge = count > 120
    const isHuge = count > 350
    // 按度数渐隐标签：大图只给「枢纽」节点显示标签，减少杂乱
    const labelMin = count > 60 ? 3 : 1

    // 聚类气泡背景（bubble-sets）：逐帧重算等高线开销大，大图禁用
    const visibleIds = new Set(data.nodes.map((n) => n.id))
    const bubblePlugins = (isLarge ? [] : view.clusters)
      .map((c) => ({ c, members: c.members.filter((m) => visibleIds.has(m)) }))
      .filter(({ members }) => members.length >= 2)
      .map(({ c, members }) => ({
        type: 'bubble-sets',
        key: `bubble-${c.id}`,
        members,
        fill: c.color,
        fillOpacity: dark ? 0.12 : 0.08,
        stroke: c.color,
        strokeOpacity: 0.4,
      }))

    const graph = new Graph({
      container,
      // 关闭内置 autoResize：由组件自身的 ResizeObserver / resizeKey 统一做 resize + fitView，
      // 避免两套 resize 机制竞争导致切换视图后画布尺寸/居中不更新
      autoResize: false,
      autoFit: 'view',
      animation: !isLarge,
      data: structuredClone(data),
      node: {
        style: {
          size: (d: Any) => d.data.size,
          fill: (d: Any) => d.data.color,
          stroke: canvasBg,
          lineWidth: 1.5,
          shadowColor: (d: Any) => d.data.color,
          shadowBlur: isLarge ? 0 : dark ? 16 : 6,
          labelText: (d: Any) => (d.data.degree >= labelMin ? d.data.label : ''),
          labelFontSize: 11,
          labelFill,
          labelPlacement: 'bottom',
          labelBackground: false,
        },
        state: {
          active: {
            lineWidth: 3,
            stroke: theme.accentSoft,
            shadowBlur: 28,
            halo: true,
            labelText: (d: Any) => d.data.label,
          },
          selected: {
            lineWidth: 3,
            stroke: theme.accent,
            shadowBlur: 28,
            halo: true,
            labelText: (d: Any) => d.data.label,
          },
          inactive: { fillOpacity: 0.12, labelOpacity: 0.1, shadowBlur: 0 },
        },
        animation: isLarge ? false : { enter: [{ fields: ['opacity', 'size'], duration: 600 }] },
      },
      edge: {
        type: 'quadratic',
        style: {
          stroke: (d: Any) => d.data.color,
          strokeOpacity: dark ? 0.5 : 0.65,
          endArrow: true,
          lineWidth: 1,
          labelText: (d: Any) => d.data.predicate,
          labelFontSize: 9,
          labelFill,
          labelOpacity: 0,
        },
        state: {
          active: {
            stroke: theme.accent,
            strokeOpacity: 1,
            lineWidth: 2,
            labelOpacity: 1,
            lineDash: [8, 6],
          },
          inactive: { strokeOpacity: 0.06, labelOpacity: 0 },
        },
      },
      layout: LAYOUTS[layout],
      behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
      plugins: [
        ...bubblePlugins,
        {
          type: 'tooltip',
          key: 'tooltip',
          getContent: (_e: unknown, items: Any[]) => {
            const it = items?.[0]
            if (!it) return ''
            const label = it.data?.predicate
              ? `${it.data.sourceLabel ?? it.source} —${it.data.predicate}→ ${it.data.targetLabel ?? it.target}`
              : it.data?.label || it.id
            return `<div style="padding:4px 8px;font-size:12px">${label}</div>`
          },
        },
      ],
    })
    graphRef.current = graph
    graph.render()

    const emptyMap = () => {
      const map: Record<string, string[]> = {}
      data.nodes.forEach((n) => (map[n.id] = []))
      data.edges.forEach((e) => (map[e.id] = []))
      return map
    }

    // 根据当前「选中项」（多选）应用持久高亮 + 聚焦
    const applySelection = () => {
      const sels = selectionsRef.current
      const map = emptyMap()
      if (sels.length === 0) {
        activeEdgesRef.current = []
        try {
          graph.setElementState(map)
        } catch {
          /* ignore */
        }
        return
      }
      const selectedNodes = new Set<string>()
      const activeNodes = new Set<string>()
      const activeEdges = new Set<string>()
      for (const sel of sels) {
        if (sel.type === 'node') {
          selectedNodes.add(sel.id)
          activeNodes.add(sel.id)
          try {
            graph.getNeighborNodesData(sel.id).forEach((d: Any) => activeNodes.add(d.id))
          } catch {
            /* ignore */
          }
          try {
            graph.getRelatedEdgesData(sel.id).forEach((d: Any) => activeEdges.add(d.id))
          } catch {
            /* ignore */
          }
        } else {
          const e = data.edges.find((x) => x.id === sel.id)
          if (e) {
            activeEdges.add(e.id)
            activeNodes.add(e.source)
            activeNodes.add(e.target)
          }
        }
      }
      data.nodes.forEach(
        (n) =>
          (map[n.id] = selectedNodes.has(n.id)
            ? ['selected']
            : activeNodes.has(n.id)
              ? ['active']
              : ['inactive']),
      )
      data.edges.forEach((e) => (map[e.id] = activeEdges.has(e.id) ? ['active'] : ['inactive']))
      // 选中态用静态高亮（虚线），不参与逐帧动画——避免持续重绘导致缩放/拖动卡顿
      activeEdgesRef.current = []
      try {
        graph.setElementState(map)
      } catch {
        /* ignore */
      }
      // 动态缩放：把高亮子集尽可能大地居中显示
      const focusIds = [...new Set<string>([...selectedNodes, ...activeNodes])]
      if (focusIds.length) fitToSelection(focusIds)
    }

    // 计算选中子集的世界坐标包围盒，缩放铺满视图（留边距）再居中
    const fitToSelection = (ids: string[]) => {
      try {
        const pts: number[][] = []
        ids.forEach((id) => {
          let p: Any = null
          try {
            p = graph.getElementPosition(id)
          } catch {
            /* ignore */
          }
          if (!p) {
            const d: Any = graph.getNodeData(id)
            if (d?.style && d.style.x != null) p = [d.style.x, d.style.y]
          }
          if (p && p[0] != null && p[1] != null) pts.push([p[0], p[1]])
        })
        if (!pts.length) {
          graph.focusElement(ids, { duration: 400 })
          return
        }
        let minX = Infinity,
          minY = Infinity,
          maxX = -Infinity,
          maxY = -Infinity
        pts.forEach(([x, y]) => {
          minX = Math.min(minX, x)
          minY = Math.min(minY, y)
          maxX = Math.max(maxX, x)
          maxY = Math.max(maxY, y)
        })
        const pad = 56
        const bw = Math.max(maxX - minX, 1)
        const bh = Math.max(maxY - minY, 1)
        const vw = container.clientWidth || 800
        const vh = container.clientHeight || 600
        const target = Math.max(
          0.2,
          Math.min(3, Math.min((vw - 2 * pad) / bw, (vh - 2 * pad) / bh)),
        )
        graph.zoomTo(target, false)
        graph.focusElement(ids, { duration: 400 })
      } catch {
        try {
          graph.focusElement(ids, { duration: 400 })
        } catch {
          /* ignore */
        }
      }
    }
    applySelRef.current = applySelection

    const hover = (nodeId: string) => {
      const nb = new Set<string>([nodeId])
      try {
        graph.getNeighborNodesData(nodeId).forEach((d: Any) => nb.add(d.id))
      } catch {
        /* ignore */
      }
      const re = new Set<string>()
      try {
        graph.getRelatedEdgesData(nodeId).forEach((d: Any) => re.add(d.id))
      } catch {
        /* ignore */
      }
      activeEdgesRef.current = [...re]
      const map: Record<string, string[]> = {}
      data.nodes.forEach((n) => (map[n.id] = nb.has(n.id) ? ['active'] : ['inactive']))
      data.edges.forEach((e) => (map[e.id] = re.has(e.id) ? ['active'] : ['inactive']))
      graph.setElementState(map)
    }

    graph.on('node:pointerenter', (e: Any) => hover(e.target.id))
    graph.on('node:pointerleave', () => applySelection())
    graph.on('node:click', (e: Any) => {
      const id = e.target.id
      const node = view.nodes.find((n) => n.id === id)
      toggleSelection(
        { type: 'node', id },
        node ? { kind: 'node', data: node.raw, type: node.cluster, color: node.color } : null,
      )
    })
    graph.on('edge:click', (e: Any) => {
      const id = e.target.id
      const edge = view.edges.find((x) => x.id === id)
      toggleSelection({ type: 'edge', id }, edge ? { kind: 'edge', edge } : null)
    })
    graph.on('canvas:click', () => clearSelections())
    graph.on('node:dblclick', (e: Any) => {
      const id = e.target.id
      const collapsed = collapsedRef.current
      const leaf = graph
        .getNeighborNodesData(id)
        .filter((nb: Any) => graph.getNeighborNodesData(nb.id).length === 1)
        .map((nb: Any) => nb.id)
      if (leaf.length === 0) return
      if (collapsed.has(id)) {
        graph.showElement(leaf)
        collapsed.delete(id)
      } else {
        graph.hideElement(leaf)
        collapsed.add(id)
      }
    })

    // 自定义小地图：把全图缩略画到右下角的 canvas，并标出当前视口范围
    const drawMinimap = () => {
      const cv = miniRef.current
      if (!cv) return
      const ctx = cv.getContext('2d')
      if (!ctx) return
      const W = cv.width
      const H = cv.height
      const pad = 8
      ctx.clearRect(0, 0, W, H)
      const ns = data.nodes
        .map((n) => {
          let p: Any = null
          try {
            p = graph.getElementPosition(n.id)
          } catch {
            /* ignore */
          }
          return p && p[0] != null ? { x: p[0], y: p[1], c: n.data.color } : null
        })
        .filter(Boolean) as { x: number; y: number; c: string }[]
      if (!ns.length) return
      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity
      ns.forEach((p) => {
        minX = Math.min(minX, p.x)
        minY = Math.min(minY, p.y)
        maxX = Math.max(maxX, p.x)
        maxY = Math.max(maxY, p.y)
      })
      const bw = Math.max(maxX - minX, 1)
      const bh = Math.max(maxY - minY, 1)
      const s = Math.min((W - 2 * pad) / bw, (H - 2 * pad) / bh)
      const ox = (W - bw * s) / 2 - minX * s
      const oy = (H - bh * s) / 2 - minY * s
      const mx = (x: number) => x * s + ox
      const my = (y: number) => y * s + oy
      ns.forEach((p) => {
        ctx.beginPath()
        ctx.arc(mx(p.x), my(p.y), 2.2, 0, 2 * Math.PI)
        ctx.fillStyle = p.c
        ctx.fill()
      })
      try {
        const [cw, ch] = graph.getSize()
        const tl = graph.getCanvasByViewport([0, 0]) as Any
        const br = graph.getCanvasByViewport([cw, ch]) as Any
        ctx.strokeStyle = dark ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.55)'
        ctx.lineWidth = 1
        ctx.strokeRect(mx(tl[0]), my(tl[1]), (br[0] - tl[0]) * s, (br[1] - tl[1]) * s)
      } catch {
        /* ignore */
      }
    }
    // 小地图用 rAF 合并：aftertransform 在拖动/缩放时高频触发，不能每次同步重画全图节点
    let miniRaf = 0
    const scheduleMinimap = () => {
      if (miniRaf) return
      miniRaf = requestAnimationFrame(() => {
        miniRaf = 0
        drawMinimap()
      })
    }
    graph.on('afterrender', scheduleMinimap)
    graph.on('aftertransform', scheduleMinimap)
    const miniTimers = [400, 900, 1600, 2600].map((t) => window.setTimeout(drawMinimap, t))

    // 图谱(重)建后，恢复当前选中项的高亮
    applySelection()

    // 活跃边「粒子流」：对当前高亮边做行进虚线动画。graph.draw() 是全图重绘，
    // 大图代价高 → 超大图直接禁用，其余降频到 90ms
    let off = 0
    const timer = isHuge
      ? 0
      : window.setInterval(() => {
          const ids = activeEdgesRef.current
          if (!ids.length) return
          off = (off + 1) % 14
          try {
            graph.updateEdgeData(ids.map((id) => ({ id, style: { lineDashOffset: -off } })))
            graph.draw()
          } catch {
            /* ignore */
          }
        }, 90)

    return () => {
      window.clearInterval(timer)
      if (miniRaf) cancelAnimationFrame(miniRaf)
      miniTimers.forEach((t) => window.clearTimeout(t))
      graph.destroy()
      graphRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, layout, dark, theme])

  // 选中项联动：高亮 + 聚焦
  useEffect(() => {
    applySelRef.current()
  }, [selections])

  // 搜索高亮
  useEffect(() => {
    const graph = graphRef.current
    if (!graph || !hasData) return
    const q = search.trim().toLowerCase()
    const map: Record<string, string[]> = {}
    if (!q) {
      data.nodes.forEach((n) => (map[n.id] = []))
      data.edges.forEach((e) => (map[e.id] = []))
    } else {
      data.nodes.forEach(
        (n) => (map[n.id] = n.data.label.toLowerCase().includes(q) ? ['active'] : ['inactive']),
      )
      data.edges.forEach((e) => (map[e.id] = ['inactive']))
    }
    try {
      graph.setElementState(map)
    } catch {
      /* ignore */
    }
  }, [search, data, hasData])

  // 容器尺寸变化（切换 图谱/双栏/工作台 视图）后重新适配图谱视图。
  // autoResize 只会同步画布尺寸、不会重新居中铺满，需手动 fitView。
  useEffect(() => {
    const el = wrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let timer: ReturnType<typeof setTimeout> | null = null
    let first = true
    const ro = new ResizeObserver(() => {
      if (first) {
        first = false // 跳过初次挂载触发
        return
      }
      if (timer) clearTimeout(timer)
      // 等宽度过渡(~300ms)结束后再 fit，避免过程中反复抖动
      timer = setTimeout(() => {
        const g = graphRef.current
        const w = el.clientWidth
        const h = el.clientHeight
        if (!g || w === 0) return
        // 先显式把画布同步到容器新尺寸（不依赖 autoResize 的触发时序），再居中铺满
        Promise.resolve()
          .then(() => g.resize(w, h))
          .then(() => g.fitView())
          .catch(() => {
            /* ignore */
          })
      }, 360)
    })
    ro.observe(el)
    return () => {
      if (timer) clearTimeout(timer)
      ro.disconnect()
    }
  }, [])

  // 父级视图/布局切换（resizeKey 变化）后，确定性地 resize + 重新适配。
  // 不依赖 ResizeObserver 是否触发；等过渡(~300ms)结束再执行。
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const id = window.setTimeout(() => {
      const g = graphRef.current
      const w = el.clientWidth
      const h = el.clientHeight
      if (!g || w === 0) return
      Promise.resolve()
        .then(() => g.resize(w, h))
        .then(() => g.fitView())
        .catch(() => {
          /* ignore */
        })
    }, 360)
    return () => window.clearTimeout(id)
  }, [resizeKey])

  const hint =
    currentPhase === 1
      ? t('graph.realtimeUpdating')
      : isSimulating
        ? t('graph.graphMemoryRealtime')
        : null

  return (
    <div className="relative h-full w-full" style={{ backgroundColor: canvasBg }}>
      <div ref={wrapRef} className="h-full w-full" />

      {/* 工具栏（左上） */}
      {hasData && (
        <div className="border-border/60 bg-card/70 absolute left-3 top-3 z-20 flex items-center gap-1.5 rounded-xl border p-1.5 shadow-lg backdrop-blur-xl">
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            title={t('graph.zoomIn')}
            onClick={() => graphRef.current?.zoomBy(1.2)}
          >
            <Plus className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            title={t('graph.zoomOut')}
            onClick={() => graphRef.current?.zoomBy(0.83)}
          >
            <Minus className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            title={t('graph.fitView')}
            onClick={() => graphRef.current?.fitView()}
          >
            <Maximize className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            title={t('graph.resetGraph')}
            onClick={() => {
              collapsedRef.current.clear()
              graphRef.current?.render()
            }}
          >
            <RotateCcw className="size-4" />
          </Button>
          <Select value={layout} onValueChange={(v) => setLayout(v as LayoutKind)}>
            <SelectTrigger className="h-7 w-24 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="d3-force">{t('graph.layoutForce')}</SelectItem>
              <SelectItem value="radial">{t('graph.layoutRadial')}</SelectItem>
              <SelectItem value="concentric">{t('graph.layoutConcentric')}</SelectItem>
              <SelectItem value="antv-dagre">{t('graph.layoutDagre')}</SelectItem>
            </SelectContent>
          </Select>
          <label className="text-muted-foreground flex items-center gap-1.5 px-1.5 text-xs">
            <input
              type="checkbox"
              checked={hideIsolated}
              onChange={(e) => setHideIsolated(e.target.checked)}
            />
            {t('graph.hideIsolated')}
          </label>
        </div>
      )}

      {/* 工具栏（右上）：搜索 / 刷新 / 最大化 */}
      <div className="absolute right-3 top-3 z-20 flex items-center gap-2">
        {hasData && (
          <div className="border-border/60 bg-card/80 flex items-center gap-1.5 rounded-md border px-2 shadow-sm backdrop-blur">
            <Search className="text-muted-foreground size-3.5" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('graph.searchPlaceholder')}
              className="h-7 w-32 bg-transparent text-xs outline-none"
            />
          </div>
        )}
        <Button
          variant="outline"
          size="icon"
          onClick={onRefresh}
          disabled={loading}
          title={t('graph.refreshGraph')}
          className="bg-background"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={onToggleMaximize}
          title={t('graph.toggleMaximize')}
          className="bg-background"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
      </div>

      {/* 自定义小地图 */}
      {hasData && (
        <canvas
          ref={miniRef}
          width={200}
          height={130}
          className="border-border/60 bg-card/90 absolute bottom-3 right-3 rounded-lg border shadow-xl backdrop-blur"
        />
      )}

      {/* 图例（左下） */}
      {hasData && (
        <GraphLegend
          typeColors={typeColors}
          nodeCount={view.nodes.length}
          edgeCount={view.edges.length}
        />
      )}

      {/* 实时更新提示 */}
      {hasData && hint && <GraphRealtimeHint hint={hint} />}

      {/* 空状态 */}
      {!hasData && !loading && (
        <div className="absolute inset-0">
          <EmptyState
            icon={Network}
            title={t('graph.noData')}
            description={t('graph.noDataDesc')}
          />
        </div>
      )}

      {/* 详情面板 */}
      {selected && (
        <GraphDetailShell
          title={selected.kind === 'node' ? t('graph.nodeDetails') : t('graph.relationship')}
          badge={
            selected.kind === 'node' ? { label: selected.type, color: selected.color } : undefined
          }
          onClose={() => setSelected(null)}
          className="z-30"
        >
          {selected.kind === 'node' ? (
            <NodeDetail data={selected.data} t={t} />
          ) : (
            <EdgeDetail
              data={{
                ...selected.edge.raw,
                source_name: selected.edge.sourceLabel,
                target_name: selected.edge.targetLabel,
              }}
              expanded={expandedLoops}
              onToggle={toggleLoop}
              t={t}
            />
          )}
        </GraphDetailShell>
      )}
    </div>
  )
}
