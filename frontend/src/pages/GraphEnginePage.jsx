import { useState, useEffect, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { listGraphs, getGraph, ingestBuiltinFile, getSyntheticFiles } from '../api/client'
import {
    GitBranch, Server, DollarSign, Activity, TrendingUp,
    ChevronDown, ZoomIn, ZoomOut, Maximize, X
} from 'lucide-react'

const TYPE_COLORS = {
    service: '#2563eb', database: '#d97706', cache: '#059669',
    queue: '#7c3aed', load_balancer: '#0891b2', storage: '#ea580c',
    serverless: '#ca8a04', cdn: '#db2777', search: '#0d9488',
    batch: '#9333ea',
}

function NodeDetailPanel({ node, onClose }) {
    if (!node) return null
    return (
        <div className="absolute top-4 right-4 w-80 bg-white border border-gray-200 rounded-xl shadow-lg p-5 z-20 animate-fade-in-up">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: TYPE_COLORS[node.type] || '#2563eb' }} />
                    <h3 className="font-bold text-gray-900 text-sm">{node.name || node.id}</h3>
                </div>
                <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-gray-500 mb-4 capitalize">{node.type} • {node.owner || 'unknown'}</p>
            <div className="grid grid-cols-2 gap-2">
                {[
                    { label: 'Monthly Cost', value: `$${node.cost?.toLocaleString() || 0}` },
                    { label: 'Degree Centrality', value: (node.degree_centrality || 0).toFixed(3) },
                    { label: 'Betweenness', value: (node.betweenness_centrality || 0).toFixed(3) },
                    { label: 'Cost Share', value: `${((node.cost_share || 0) * 100).toFixed(1)}%` },
                ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-lg p-2.5">
                        <p className="text-[10px] text-gray-400 uppercase mb-0.5">{label}</p>
                        <p className="text-sm font-bold text-gray-900">{value}</p>
                    </div>
                ))}
            </div>
            <div className="mt-3 p-3 bg-blue-50 border border-blue-100 rounded-lg">
                <p className="text-xs text-blue-700 leading-relaxed">
                    {(node.betweenness_centrality || 0) > 0.1
                        ? `⚠️ High betweenness — this AWS resource is a critical intermediary. Set up CloudWatch alarms.`
                        : (node.degree_centrality || 0) > 0.3
                            ? `🔗 High connectivity — this resource connects many services. Consider Multi-AZ deployment.`
                            : `✅ Moderate connectivity. No structural risk from this resource.`
                    }
                </p>
            </div>
        </div>
    )
}

export default function GraphEnginePage() {
    const [graphs, setGraphs] = useState([])
    const [selectedGraph, setSelectedGraph] = useState(null)
    const [graphData, setGraphData] = useState(null)
    const [archInfo, setArchInfo] = useState(null)
    const [selectedNode, setSelectedNode] = useState(null)
    const [loading, setLoading] = useState(false)
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const [dimensions, setDimensions] = useState({ width: 1000, height: 700 })
    const containerRef = useRef()
    const fgRef = useRef()

    useEffect(() => { loadGraphs() }, [])

    async function loadGraphs() {
        try {
            const res = await listGraphs()
            setGraphs(res.data.architectures || [])
        } catch {
            try {
                const files = await getSyntheticFiles()
                if (files.data?.files?.length > 0) {
                    await ingestBuiltinFile(files.data.files[0].filename)
                    const res = await listGraphs()
                    setGraphs(res.data.architectures || [])
                }
            } catch { }
        }
    }

    async function selectArchitecture(arch) {
        setLoading(true); setDropdownOpen(false); setSelectedNode(null)
        try {
            const res = await getGraph(arch.id)
            setSelectedGraph(arch); setArchInfo(res.data)
            setGraphData({
                nodes: (res.data.nodes || []).map(n => ({ ...n, id: n.id || n.name })),
                links: (res.data.edges || []).map(e => ({ source: e.source, target: e.target, type: e.type, weight: e.weight || 1 }))
            })
        } catch { }
        setLoading(false)
    }

    useEffect(() => {
        if (!containerRef.current) return
        const obs = new ResizeObserver(([e]) => setDimensions({ width: e.contentRect.width, height: 700 }))
        obs.observe(containerRef.current)
        return () => obs.disconnect()
    }, [])

    useEffect(() => {
        if (fgRef.current && graphData) {
            fgRef.current.d3Force('charge').strength(-350).distanceMax(500)
            fgRef.current.d3Force('link').distance(160)
            fgRef.current.d3Force('center').strength(0.04)
            fgRef.current.d3ReheatSimulation()
        }
    }, [graphData])

    const nodeCanvasObject = useCallback((node, ctx, gs) => {
        const r = Math.max(5, Math.sqrt((node.cost || 100) / 60))
        const c = TYPE_COLORS[node.type] || '#2563eb'
        if (selectedNode?.id === node.id) { ctx.beginPath(); ctx.arc(node.x, node.y, r + 4, 0, Math.PI * 2); ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 2; ctx.stroke() }
        ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI * 2); ctx.fillStyle = c; ctx.fill()
        if (gs > 0.6) { ctx.font = `${Math.max(10, 11 / gs)}px Inter`; ctx.fillStyle = '#6b7280'; ctx.textAlign = 'center'; ctx.fillText(node.name || node.id, node.x, node.y + r + 12) }
    }, [selectedNode])

    const stats = archInfo ? {
        services: archInfo.nodes?.length || 0,
        deps: archInfo.edges?.length || 0,
        cost: archInfo.nodes?.reduce((s, n) => s + (n.cost || 0), 0) || 0,
        density: archInfo.density || 0,
    } : null

    return (
        <div className="max-w-7xl mx-auto px-6 py-10">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Graph Engine</h1>
                    <p className="text-sm text-gray-500 mt-0.5">Interactive AWS dependency graph — click nodes for details</p>
                </div>
                <div className="relative">
                    <button onClick={() => setDropdownOpen(!dropdownOpen)} className="btn-outline min-w-[200px] justify-between">
                        <span className="text-sm">{selectedGraph?.name || 'Select Architecture'}</span>
                        <ChevronDown className="w-4 h-4" />
                    </button>
                    {dropdownOpen && (
                        <div className="absolute right-0 mt-2 w-64 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-30 max-h-64 overflow-y-auto">
                            {graphs.map(g => (
                                <button key={g.id} onClick={() => selectArchitecture(g)}
                                    className="w-full text-left px-3 py-2 rounded-lg text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors flex justify-between">
                                    <span>{g.name}</span><span className="text-xs text-gray-400">{g.service_count} svc</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {stats && (
                <div className="grid grid-cols-4 gap-3 mb-4">
                    {[
                        { label: 'Services', value: stats.services }, { label: 'Dependencies', value: stats.deps },
                        { label: 'Monthly Cost', value: `$${stats.cost.toLocaleString()}` }, { label: 'Density', value: stats.density.toFixed(3) },
                    ].map(({ label, value }) => (
                        <div key={label} className="card px-4 py-2.5 flex items-center gap-3">
                            <div><p className="text-sm font-bold text-gray-900">{value}</p><p className="text-[10px] text-gray-400 uppercase">{label}</p></div>
                        </div>
                    ))}
                </div>
            )}

            <div ref={containerRef} className="relative card overflow-hidden" style={{ height: 700 }}>
                {!graphData ? (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="text-center"><GitBranch className="w-14 h-14 text-gray-300 mx-auto mb-3" /><p className="text-gray-400 text-sm">Select an architecture</p></div>
                    </div>
                ) : (
                    <>
                        <ForceGraph2D ref={fgRef} graphData={graphData} width={dimensions.width} height={dimensions.height}
                            backgroundColor="#ffffff" nodeCanvasObject={nodeCanvasObject}
                            linkWidth={e => Math.max(1, (e.weight || 0.5) * 1.5)} linkColor={() => 'rgba(209,213,219,0.6)'}
                            linkDirectionalArrowLength={5} linkDirectionalArrowRelPos={1}
                            linkDirectionalParticles={1} linkDirectionalParticleWidth={2} linkDirectionalParticleColor={() => '#93c5fd'}
                            onNodeClick={node => setSelectedNode(node)}
                            cooldownTicks={100} d3AlphaDecay={0.015} d3VelocityDecay={0.25}
                            warmupTicks={50} onEngineStop={() => fgRef.current?.zoomToFit(400, 60)} />
                        <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
                        <div className="absolute bottom-3 right-3 flex flex-col gap-1">
                            <button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.3, 300)} className="w-8 h-8 bg-white border border-gray-200 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 shadow-sm"><ZoomIn className="w-3.5 h-3.5" /></button>
                            <button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.3, 300)} className="w-8 h-8 bg-white border border-gray-200 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 shadow-sm"><ZoomOut className="w-3.5 h-3.5" /></button>
                            <button onClick={() => fgRef.current?.zoomToFit(400, 60)} className="w-8 h-8 bg-white border border-gray-200 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 shadow-sm"><Maximize className="w-3.5 h-3.5" /></button>
                        </div>
                    </>
                )}
            </div>

            {graphData && (
                <div className="mt-3 card px-5 py-2.5 flex flex-wrap gap-4">
                    {Object.entries(TYPE_COLORS).map(([type, color]) => (
                        <div key={type} className="flex items-center gap-1.5">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                            <span className="text-xs text-gray-500 capitalize">{type.replace('_', ' ')}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
