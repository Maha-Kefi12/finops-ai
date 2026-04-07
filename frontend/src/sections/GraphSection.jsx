import { useState, useRef, useCallback, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { X, Network, Info, DollarSign, Activity, Link2, AlertTriangle, BarChart3 } from 'lucide-react'

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

const GRAPH_THEORY = [
    {
        title: 'Degree Centrality',
        icon: Link2,
        color: 'text-indigo-400',
        bg: 'bg-indigo-900/20 border-indigo-500/20',
        description: 'Measures how connected a node is in the graph. A high degree centrality means the service has many direct dependencies — it connects to or is connected by many other services. Services with high degree centrality are architectural hubs.',
        formula: 'C_D(v) = deg(v) / (n-1)',
    },
    {
        title: 'Betweenness Centrality',
        icon: Activity,
        color: 'text-amber-400',
        bg: 'bg-amber-900/20 border-amber-500/20',
        description: 'Quantifies how often a node lies on the shortest path between two other nodes. High betweenness = critical bottleneck. If this service fails, communication between many other services is disrupted. These are your highest-risk points of failure.',
        formula: 'C_B(v) = Σ σ_st(v) / σ_st',
    },
    {
        title: 'Cost Hotspot Analysis',
        icon: DollarSign,
        color: 'text-emerald-400',
        bg: 'bg-emerald-900/20 border-emerald-500/20',
        description: 'Identifies the services that consume the highest share of the total monthly cost. Combined with centrality, this reveals services that are both expensive AND critical — prime candidates for optimization or Right-sizing.',
        formula: 'Cost Share = cost(v) / Σ cost(all)',
    },
    {
        title: 'Graph Density & DAG',
        icon: Network,
        color: 'text-purple-400',
        bg: 'bg-purple-900/20 border-purple-500/20',
        description: 'Graph density measures how many of the possible edges actually exist. A Directed Acyclic Graph (DAG) has no cycles — meaning no circular dependencies. Circular dependencies increase complexity and make failures cascade unpredictably.',
        formula: 'D = |E| / (|V| × (|V|-1))',
    },
]

function formatCost(v) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact' }).format(v)
}

function formatCostFull(v) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}

function StatBadge({ icon: Icon, label, value, color }) {
    return (
        <div className="flex items-center gap-2 bg-gray-800/60 px-3 py-2 rounded-lg">
            <Icon className={`w-4 h-4 ${color}`} />
            <span className="text-xs text-gray-400">{label}</span>
            <span className="text-xs font-bold text-white ml-auto">{value}</span>
        </div>
    )
}

function NodeDetailPanel({ node, onClose }) {
    if (!node) return null
    const isHighBetweenness = node.betweenness_centrality > 0.1
    const isHighCost = node.cost_share > 20

    return (
        <div className="absolute top-4 right-4 card p-5 w-80 z-20 space-y-4 shadow-2xl shadow-black/40 animate-fade-in-up" style={{ animationDelay: '0s', opacity: 1 }}>
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full" style={{ background: node.color || '#6b7280' }} />
                    <div>
                        <h3 className="text-sm font-bold text-white">{node.name}</h3>
                        <span className="text-xs text-gray-500 capitalize">{node.type?.replace('_', ' ')}</span>
                    </div>
                </div>
                <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
                    <X className="w-4 h-4" />
                </button>
            </div>

            {/* Warnings */}
            {(isHighBetweenness || isHighCost) && (
                <div className="flex flex-wrap gap-2">
                    {isHighBetweenness && (
                        <span className="badge bg-amber-900/40 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" /> Critical Bottleneck
                        </span>
                    )}
                    {isHighCost && (
                        <span className="badge bg-red-900/40 text-red-300 border border-red-500/30 flex items-center gap-1">
                            <DollarSign className="w-3 h-3" /> Cost Hotspot
                        </span>
                    )}
                </div>
            )}

            {/* Metrics grid */}
            <div className="grid grid-cols-2 gap-2">
                {[
                    { label: 'Monthly Cost', value: formatCost(node.cost_monthly || 0), color: 'text-amber-400' },
                    { label: 'Cost Share', value: `${(node.cost_share || 0).toFixed(1)}%`, color: 'text-emerald-400' },
                    { label: 'Degree Cent.', value: (node.degree_centrality || 0).toFixed(3), color: 'text-indigo-400' },
                    { label: 'Betweenness', value: (node.betweenness_centrality || 0).toFixed(3), color: 'text-purple-400' },
                    { label: 'In-degree', value: node.in_degree || 0, color: 'text-blue-400' },
                    { label: 'Out-degree', value: node.out_degree || 0, color: 'text-cyan-400' },
                    { label: 'Owner', value: node.owner || '—', color: 'text-gray-400' },
                    { label: 'Environment', value: node.environment || 'prod', color: 'text-gray-400' },
                ].map(({ label, value, color }) => (
                    <div key={label} className="bg-gray-800/50 rounded-lg px-3 py-2">
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
                        <p className={`text-xs font-bold mt-0.5 truncate ${color}`}>{value}</p>
                    </div>
                ))}
            </div>

            {/* Attributes */}
            {node.attributes && Object.keys(node.attributes).filter(k => node.attributes[k] != null).length > 0 && (
                <div className="border-t border-gray-700/50 pt-3">
                    <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">AWS Attributes</p>
                    <div className="space-y-1">
                        {Object.entries(node.attributes).filter(([, v]) => v != null).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-xs">
                                <span className="text-gray-500">{k.replace(/_/g, ' ')}</span>
                                <span className="text-gray-300 font-medium">{typeof v === 'number' ? v.toLocaleString() : String(v)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Interpretation */}
            <div className="border-t border-gray-700/50 pt-3">
                <div className="flex items-center gap-1.5 mb-1.5">
                    <Info className="w-3.5 h-3.5 text-indigo-400" />
                    <p className="text-[10px] uppercase tracking-wider text-gray-500">Interpretation</p>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed">
                    {isHighBetweenness
                        ? `This service is a critical bottleneck — it lies on many shortest paths between other services. If "${node.name}" fails, it will disrupt communication across the architecture.`
                        : node.degree_centrality > 0.3
                            ? `"${node.name}" is a well-connected hub with high degree centrality, acting as a nexus for multiple services.`
                            : `"${node.name}" is a peripheral service with limited direct connections.`
                    }
                    {isHighCost
                        ? ` It also accounts for ${(node.cost_share || 0).toFixed(1)}% of total cost — a prime optimization target.`
                        : ''
                    }
                </p>
            </div>
        </div>
    )
}

export default function GraphSection({ graphData, archInfo }) {
    const fgRef = useRef()
    const containerRef = useRef()
    const [dimensions, setDimensions] = useState({ width: 1000, height: 900 })
    const [selectedNode, setSelectedNode] = useState(null)
    const [criticalNodeIds, setCriticalNodeIds] = useState(new Set())

    useEffect(() => {
        if (graphData?.metrics?.critical_nodes) {
            setCriticalNodeIds(new Set(graphData.metrics.critical_nodes))
        }
    }, [graphData])

    // Apply strong repulsion force so nodes spread out
    useEffect(() => {
        if (fgRef.current && graphData) {
            fgRef.current.d3Force('charge').strength(-400).distanceMax(600)
            fgRef.current.d3Force('link').distance(180)
            fgRef.current.d3Force('center').strength(0.03)
            fgRef.current.d3ReheatSimulation()
        }
    }, [graphData])

    useEffect(() => {
        const obs = new ResizeObserver(([e]) => {
            const { width } = e.contentRect
            setDimensions({ width, height: 900 })
        })
        if (containerRef.current) obs.observe(containerRef.current)
        return () => obs.disconnect()
    }, [])

    const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
        const size = Math.max(5, (node.val || 6))
        const isCritical = criticalNodeIds.has(node.id)
        const isSelected = selectedNode?.id === node.id

        // Outer glow for critical nodes
        if (isCritical) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, size + 6, 0, 2 * Math.PI)
            ctx.fillStyle = 'rgba(251, 191, 36, 0.12)'
            ctx.fill()
            ctx.beginPath()
            ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI)
            ctx.fillStyle = 'rgba(251, 191, 36, 0.08)'
            ctx.fill()
        }

        // Node circle
        ctx.beginPath()
        ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
        ctx.fillStyle = node.color || '#6366f1'
        ctx.fill()

        // Inner highlight
        ctx.beginPath()
        ctx.arc(node.x, node.y, size * 0.5, 0, 2 * Math.PI)
        ctx.fillStyle = 'rgba(255,255,255,0.15)'
        ctx.fill()

        // Selection ring
        if (isSelected) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI)
            ctx.strokeStyle = 'rgba(255,255,255,0.9)'
            ctx.lineWidth = 2
            ctx.stroke()
        }

        // Label
        if (globalScale >= 0.5) {
            const fontSize = Math.max(9, 11 / globalScale)
            ctx.font = `500 ${fontSize}px Inter, sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = 'rgba(255,255,255,0.8)'
            const label = node.name?.length > 14 ? node.name.slice(0, 14) + '…' : node.name
            ctx.fillText(label, node.x, node.y + size + fontSize * 0.9)
        }
    }, [selectedNode, criticalNodeIds])

    const metrics = graphData?.metrics
    const hasData = graphData && graphData.nodes?.length > 0

    return (
        <section id="graph" className="py-24 px-6">
            <div className="max-w-7xl mx-auto">
                {/* Section Header */}
                <div className="text-center mb-10">
                    <div className="inline-flex items-center gap-2 bg-indigo-900/20 border border-indigo-500/25 px-3 py-1.5 rounded-full mb-4">
                        <Network className="w-3.5 h-3.5 text-indigo-400" />
                        <span className="text-xs font-medium text-indigo-300">Graph Engine</span>
                    </div>
                    <h2 className="section-title">Architecture Dependency Graph</h2>
                    <p className="section-subtitle mx-auto">
                        Interactive force-directed visualization. Click any node to explore its graph theory metrics and AWS details.
                    </p>
                </div>

                {!hasData ? (
                    <div className="card p-20 flex flex-col items-center justify-center gap-4 text-center">
                        <Network className="w-16 h-16 text-gray-800" />
                        <p className="text-gray-500 text-lg">No graph loaded yet</p>
                        <p className="text-gray-600 text-sm">Ingest an architecture above to render the dependency graph here</p>
                    </div>
                ) : (
                    <>
                        {/* Summary stats bar */}
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
                            <StatBadge icon={Network} label="Services" value={metrics?.total_services} color="text-indigo-400" />
                            <StatBadge icon={Link2} label="Dependencies" value={metrics?.total_dependencies} color="text-blue-400" />
                            <StatBadge icon={DollarSign} label="Monthly Cost" value={formatCostFull(metrics?.total_cost_monthly || 0)} color="text-amber-400" />
                            <StatBadge icon={BarChart3} label="Density" value={(metrics?.density || 0).toFixed(3)} color="text-emerald-400" />
                            <StatBadge icon={Activity} label="DAG" value={metrics?.is_dag ? 'Yes ✓' : 'No (cycles)'} color={metrics?.is_dag ? 'text-emerald-400' : 'text-red-400'} />
                        </div>

                        {/* Graph canvas */}
                        <div ref={containerRef} className="relative card overflow-hidden" style={{ height: 900 }}>
                            {/* Legend */}
                            <div className="absolute bottom-4 left-4 card p-3 text-xs space-y-1.5 z-10 bg-gray-900/90">
                                <p className="font-semibold text-gray-300 mb-2">Node Types</p>
                                {Object.entries(TYPE_COLOR).map(([type, color]) => (
                                    <div key={type} className="flex items-center gap-2">
                                        <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                                        <span className="text-gray-400 capitalize">{type.replace('_', ' ')}</span>
                                    </div>
                                ))}
                            </div>

                            <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />

                            <ForceGraph2D
                                ref={fgRef}
                                graphData={graphData}
                                width={dimensions.width}
                                height={dimensions.height}
                                backgroundColor="rgba(3, 7, 18, 0)"
                                nodeCanvasObject={nodeCanvasObject}
                                nodePointerAreaPaint={(node, color, ctx) => {
                                    const s = Math.max(5, node.val || 6)
                                    ctx.beginPath()
                                    ctx.arc(node.x, node.y, s + 3, 0, 2 * Math.PI)
                                    ctx.fillStyle = color
                                    ctx.fill()
                                }}
                                linkColor={() => 'rgba(148, 163, 184, 0.15)'}
                                linkWidth={(link) => Math.max(0.5, (link.weight || 0.5) * 1.5)}
                                linkDirectionalArrowLength={5}
                                linkDirectionalArrowRelPos={1}
                                linkDirectionalParticles={2}
                                linkDirectionalParticleWidth={1.5}
                                linkDirectionalParticleColor={() => 'rgba(99, 102, 241, 0.6)'}
                                onNodeClick={(node) => setSelectedNode(node)}
                                cooldownTicks={120}
                                d3AlphaDecay={0.015}
                                d3VelocityDecay={0.25}
                                warmupTicks={50}
                                onEngineStop={() => fgRef.current?.zoomToFit(500, 80)}
                            />
                        </div>

                        {/* Graph Theory Education Cards */}
                        <div className="mt-12">
                            <div className="text-center mb-8">
                                <h3 className="text-xl font-bold text-white">Understanding Graph Metrics</h3>
                                <p className="text-sm text-gray-400 mt-1">How graph theory reveals hidden patterns in your architecture</p>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {GRAPH_THEORY.map((item) => {
                                    const Icon = item.icon
                                    return (
                                        <div key={item.title} className={`card p-5 border ${item.bg} space-y-3`}>
                                            <div className="flex items-center gap-3">
                                                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${item.bg}`}>
                                                    <Icon className={`w-5 h-5 ${item.color}`} />
                                                </div>
                                                <h4 className="text-sm font-bold text-white">{item.title}</h4>
                                            </div>
                                            <p className="text-sm text-gray-400 leading-relaxed">{item.description}</p>
                                            <div className="bg-gray-800/60 px-3 py-2 rounded-lg">
                                                <code className="text-xs text-gray-300 font-mono">{item.formula}</code>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </section>
    )
}
