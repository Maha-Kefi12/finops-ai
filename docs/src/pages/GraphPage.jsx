import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { listGraphs, getGraph, deleteGraph } from '../api/client'
import {
    Network, ChevronDown, Trash2, X, DollarSign,
    Activity, Link2, AlertTriangle, Server
} from 'lucide-react'

const formatCost = (v) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact' }).format(v)

const TYPE_COLOR = {
    service: '#6366f1',
    database: '#10b981',
    cache: '#f59e0b',
    storage: '#3b82f6',
    serverless: '#8b5cf6',
    queue: '#ec4899',
    load_balancer: '#14b8a6',
    cdn: '#f97316',
    search: '#ef4444',
    batch: '#84cc16',
}

function Legend() {
    return (
        <div className="absolute bottom-4 left-4 card p-3 text-xs space-y-1.5 z-10">
            <p className="font-semibold text-slate-300 mb-2">Node Types</p>
            {Object.entries(TYPE_COLOR).map(([type, color]) => (
                <div key={type} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                    <span className="text-slate-400 capitalize">{type.replace('_', ' ')}</span>
                </div>
            ))}
        </div>
    )
}

function NodeDetail({ node, onClose }) {
    if (!node) return null
    return (
        <div className="absolute top-4 right-4 card p-4 w-72 z-10 space-y-3">
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: node.color || '#6b7280' }} />
                    <h3 className="text-sm font-semibold text-white truncate">{node.name}</h3>
                </div>
                <button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X className="w-4 h-4" /></button>
            </div>

            <div className="grid grid-cols-2 gap-2">
                {[
                    { label: 'Type', value: node.type },
                    { label: 'Owner', value: node.owner || '—' },
                    { label: 'Monthly Cost', value: formatCost(node.cost_monthly || 0) },
                    { label: 'Cost Share', value: `${node.cost_share?.toFixed(1) || 0}%` },
                    { label: 'Degree Centrality', value: node.degree_centrality?.toFixed(3) },
                    { label: 'Betweenness', value: node.betweenness_centrality?.toFixed(3) },
                    { label: 'In-degree', value: node.in_degree },
                    { label: 'Out-degree', value: node.out_degree },
                ].map(({ label, value }) => (
                    <div key={label} className="bg-slate-700/40 rounded-lg p-2">
                        <p className="text-xs text-slate-500">{label}</p>
                        <p className="text-xs font-semibold text-slate-200 mt-0.5 truncate">{value}</p>
                    </div>
                ))}
            </div>

            {node.attributes && Object.keys(node.attributes).length > 0 && (
                <div className="border-t border-slate-700/60 pt-2 space-y-1">
                    <p className="text-xs text-slate-500 font-medium">Attributes</p>
                    {Object.entries(node.attributes).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-xs">
                            <span className="text-slate-500">{k}</span>
                            <span className="text-slate-300">{typeof v === 'number' ? v.toLocaleString() : String(v)}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function MetricsPanel({ metrics, archInfo }) {
    if (!metrics) return null
    const formatCostFull = (v) =>
        new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
    return (
        <div className="absolute top-4 left-4 card p-4 w-60 z-10 space-y-3">
            <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-semibold text-white truncate">{archInfo?.name}</h3>
            </div>
            <div className="space-y-2">
                {[
                    { icon: Server, label: 'Services', value: metrics.total_services, color: 'text-indigo-400' },
                    { icon: Link2, label: 'Dependencies', value: metrics.total_dependencies, color: 'text-blue-400' },
                    { icon: DollarSign, label: 'Monthly Cost', value: formatCostFull(metrics.total_cost_monthly), color: 'text-amber-400' },
                    { icon: Activity, label: 'Graph Density', value: metrics.density?.toFixed(3) ?? '—', color: 'text-emerald-400' },
                ].map(({ icon: Icon, label, value, color }) => (
                    <div key={label} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Icon className={`w-3.5 h-3.5 ${color}`} />
                            <span className="text-xs text-slate-400">{label}</span>
                        </div>
                        <span className="text-xs font-semibold text-slate-200">{value}</span>
                    </div>
                ))}
            </div>
            {metrics.critical_nodes?.length > 0 && (
                <div className="border-t border-slate-700/60 pt-2">
                    <div className="flex items-center gap-1.5 mb-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                        <p className="text-xs text-slate-400 font-medium">Critical Nodes</p>
                    </div>
                    <p className="text-xs text-slate-500">Highest betweenness centrality — bottlenecks</p>
                </div>
            )}
        </div>
    )
}

export default function GraphPage() {
    const { id } = useParams()
    const navigate = useNavigate()
    const fgRef = useRef()
    const containerRef = useRef()

    const [archs, setArchs] = useState([])
    const [selectedId, setSelectedId] = useState(id || null)
    const [graphData, setGraphData] = useState(null)
    const [metrics, setMetrics] = useState(null)
    const [archInfo, setArchInfo] = useState(null)
    const [loading, setLoading] = useState(false)
    const [selectedNode, setSelectedNode] = useState(null)
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
    const [criticalNodeIds, setCriticalNodeIds] = useState(new Set())

    // Load architecture list
    useEffect(() => {
        listGraphs().then((r) => {
            const list = r.data.architectures || []
            setArchs(list)
            if (!selectedId && list.length > 0) {
                setSelectedId(list[0].id)
            }
        })
    }, [])

    // Load graph data when selected
    useEffect(() => {
        if (!selectedId) return
        setLoading(true)
        setSelectedNode(null)
        getGraph(selectedId).then((r) => {
            const d = r.data
            setGraphData({ nodes: d.nodes, links: d.links })
            setMetrics(d.metrics)
            setArchInfo(d.architecture)
            setCriticalNodeIds(new Set(d.metrics.critical_nodes || []))
        }).catch(console.error).finally(() => setLoading(false))
    }, [selectedId])

    // Responsive canvas size
    useEffect(() => {
        const obs = new ResizeObserver(([entry]) => {
            const { width, height } = entry.contentRect
            setDimensions({ width, height })
        })
        if (containerRef.current) obs.observe(containerRef.current)
        return () => obs.disconnect()
    }, [])

    const handleNodeClick = useCallback((node) => setSelectedNode(node), [])

    const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
        const label = node.name
        const size = Math.max(4, (node.val || 6))
        const isCritical = criticalNodeIds.has(node.id)
        const isSelected = selectedNode?.id === node.id

        // Glow for critical nodes
        if (isCritical) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
            ctx.fillStyle = 'rgba(251, 191, 36, 0.15)'
            ctx.fill()
        }

        // Node circle
        ctx.beginPath()
        ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
        ctx.fillStyle = node.color || '#6366f1'
        ctx.fill()

        // Selection ring
        if (isSelected) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, size + 2.5, 0, 2 * Math.PI)
            ctx.strokeStyle = 'rgba(255,255,255,0.8)'
            ctx.lineWidth = 1.5
            ctx.stroke()
        }

        // Label
        if (globalScale >= 0.6) {
            const fontSize = Math.max(8, 10 / globalScale)
            ctx.font = `${fontSize}px Inter, sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = 'rgba(255,255,255,0.85)'
            ctx.fillText(label.length > 12 ? label.slice(0, 12) + '…' : label, node.x, node.y + size + fontSize * 0.9)
        }
    }, [selectedNode, criticalNodeIds])

    const handleDelete = async () => {
        if (!selectedId || !confirm('Delete this architecture?')) return
        await deleteGraph(selectedId)
        navigate('/graph')
        setSelectedId(null)
        setGraphData(null)
        listGraphs().then((r) => setArchs(r.data.architectures || []))
    }

    return (
        <div className="flex flex-col h-full">
            {/* Toolbar */}
            <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-700/60 flex-shrink-0">
                <div className="flex items-center gap-2 flex-1">
                    <Network className="w-4 h-4 text-indigo-400" />
                    <h1 className="text-sm font-semibold text-white">Graph Explorer</h1>
                </div>

                {/* Architecture selector */}
                <div className="relative">
                    <select
                        value={selectedId || ''}
                        onChange={(e) => setSelectedId(e.target.value)}
                        className="appearance-none bg-slate-800 border border-slate-700 text-slate-300 text-sm px-3 py-1.5 pr-8 rounded-lg focus:outline-none focus:border-indigo-500 cursor-pointer"
                    >
                        <option value="">Select architecture…</option>
                        {archs.map((a) => (
                            <option key={a.id} value={a.id}>
                                {a.name} ({a.pattern})
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>

                {selectedId && (
                    <button onClick={handleDelete} className="btn-ghost text-red-400 hover:text-red-300 hover:bg-red-900/20">
                        <Trash2 className="w-4 h-4" /> Delete
                    </button>
                )}
            </div>

            {/* Graph Canvas */}
            <div ref={containerRef} className="relative flex-1 bg-slate-950">
                {!selectedId ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
                        <Network className="w-16 h-16 text-slate-800" />
                        <p className="text-slate-500">Select an architecture to explore</p>
                        <button onClick={() => navigate('/ingest')} className="btn-primary text-sm">
                            Go to Ingest
                        </button>
                    </div>
                ) : loading ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="flex flex-col items-center gap-3">
                            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                            <p className="text-slate-500 text-sm">Loading graph…</p>
                        </div>
                    </div>
                ) : graphData ? (
                    <>
                        <MetricsPanel metrics={metrics} archInfo={archInfo} />
                        <Legend />
                        <NodeDetail node={selectedNode} onClose={() => setSelectedNode(null)} />
                        <ForceGraph2D
                            ref={fgRef}
                            graphData={graphData}
                            width={dimensions.width}
                            height={dimensions.height}
                            backgroundColor="#080e1a"
                            nodeCanvasObject={nodeCanvasObject}
                            nodePointerAreaPaint={(node, color, ctx) => {
                                const size = Math.max(4, node.val || 6)
                                ctx.beginPath()
                                ctx.arc(node.x, node.y, size + 2, 0, 2 * Math.PI)
                                ctx.fillStyle = color
                                ctx.fill()
                            }}
                            linkColor={() => 'rgba(148, 163, 184, 0.25)'}
                            linkWidth={(link) => (link.weight || 0.5) * 1.5}
                            linkDirectionalArrowLength={4}
                            linkDirectionalArrowRelPos={1}
                            linkDirectionalParticles={1}
                            linkDirectionalParticleWidth={1.5}
                            linkDirectionalParticleColor={() => 'rgba(99, 102, 241, 0.7)'}
                            onNodeClick={handleNodeClick}
                            cooldownTicks={80}
                            onEngineStop={() => fgRef.current?.zoomToFit(400, 60)}
                        />
                    </>
                ) : null}
            </div>
        </div>
    )
}
