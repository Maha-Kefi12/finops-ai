import { useState, useEffect, useCallback } from 'react'
import {
    Share2, Target, Route, Boxes, Clock, Zap, Loader2, ChevronDown,
    ChevronRight, AlertCircle, Network, DollarSign, Shield
} from 'lucide-react'
import {
    listGraphs, runEgoNetwork, runPathBased, runClusterBased,
    runTemporal, runCombinedTraversal,
} from '../api/client'

const STRATEGY_META = {
    ego_network: {
        label: 'Ego Network Expansion',
        icon: Target,
        color: 'indigo',
        desc: 'BFS from a seed node to k-hop neighbors — shows local influence zone.',
    },
    path_based: {
        label: 'Path-Based Expansion',
        icon: Route,
        color: 'emerald',
        desc: 'Finds shortest & alternative paths between two nodes — reveals critical bottlenecks.',
    },
    cluster_based: {
        label: 'Cluster-Based Expansion',
        icon: Boxes,
        color: 'amber',
        desc: 'Community detection — identifies logical infrastructure clusters.',
    },
    temporal: {
        label: 'Temporal Expansion',
        icon: Clock,
        color: 'sky',
        desc: 'Time-based traversal — identifies deployment waves & stale resources.',
    },
}

const COLORS = {
    indigo: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', badge: 'bg-indigo-100 text-indigo-700', ring: 'ring-indigo-300' },
    emerald: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-700', ring: 'ring-emerald-300' },
    amber: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', badge: 'bg-amber-100 text-amber-700', ring: 'ring-amber-300' },
    sky: { bg: 'bg-sky-50', border: 'border-sky-200', text: 'text-sky-700', badge: 'bg-sky-100 text-sky-700', ring: 'ring-sky-300' },
}

export default function GraphRAGPage() {
    const [architectures, setArchitectures] = useState([])
    const [selectedArch, setSelectedArch] = useState('')
    const [selectedGraph, setSelectedGraph] = useState(null)
    const [loading, setLoading] = useState(false)
    const [results, setResults] = useState({})
    const [activeStrategy, setActiveStrategy] = useState('ego_network')
    const [expandedResult, setExpandedResult] = useState(null)

    // Strategy params
    const [seedNode, setSeedNode] = useState('')
    const [targetNode, setTargetNode] = useState('')
    const [hops, setHops] = useState(2)
    const [maxNodes, setMaxNodes] = useState(50)
    const [minCluster, setMinCluster] = useState(2)
    const [resolution, setResolution] = useState(1.0)
    const [windowHours, setWindowHours] = useState(24)

    useEffect(() => {
        listGraphs().then(r => {
            setArchitectures(r.data.architectures || [])
        }).catch(() => {})
    }, [])

    const runStrategy = useCallback(async () => {
        if (!selectedArch) return
        setLoading(true)
        try {
            let res
            switch (activeStrategy) {
                case 'ego_network':
                    res = await runEgoNetwork(selectedArch, seedNode || undefined, hops, maxNodes)
                    break
                case 'path_based':
                    res = await runPathBased(selectedArch, seedNode, targetNode)
                    break
                case 'cluster_based':
                    res = await runClusterBased(selectedArch, minCluster, resolution, seedNode || null)
                    break
                case 'temporal':
                    res = await runTemporal(selectedArch, windowHours)
                    break
                default:
                    return
            }
            setResults(prev => ({ ...prev, [activeStrategy]: res.data }))
            setExpandedResult(activeStrategy)
        } catch (err) {
            setResults(prev => ({
                ...prev,
                [activeStrategy]: { error: err.response?.data?.detail || err.message },
            }))
        } finally {
            setLoading(false)
        }
    }, [selectedArch, activeStrategy, seedNode, targetNode, hops, maxNodes, minCluster, resolution, windowHours])

    const runAll = useCallback(async () => {
        if (!selectedArch) return
        setLoading(true)
        try {
            const res = await runCombinedTraversal(
                selectedArch, seedNode || null, targetNode || null, hops, windowHours
            )
            const data = res.data
            // Split combined result into individual strategy results
            for (const [key, val] of Object.entries(data.strategies || {})) {
                setResults(prev => ({ ...prev, [key]: val }))
            }
            setResults(prev => ({ ...prev, _combined: data }))
            setExpandedResult('_combined')
        } catch (err) {
            setResults(prev => ({
                ...prev,
                _combined: { error: err.response?.data?.detail || err.message },
            }))
        } finally {
            setLoading(false)
        }
    }, [selectedArch, seedNode, targetNode, hops, windowHours])

    // Get node list for seed/target dropdowns
    const nodeList = selectedGraph?.nodes || []

    return (
        <div className="max-w-7xl mx-auto px-6 py-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow">
                        <Share2 className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-gray-900">GraphRAG Traversal Engine</h1>
                        <p className="text-xs text-gray-500">4 traversal strategies for infrastructure intelligence</p>
                    </div>
                </div>
                <button
                    onClick={runAll}
                    disabled={!selectedArch || loading}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white rounded-lg text-sm font-medium hover:from-violet-700 hover:to-indigo-700 disabled:opacity-50 shadow"
                >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                    Run All Strategies
                </button>
            </div>

            {/* Architecture & Node Selection */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {/* Arch selector */}
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Architecture</label>
                    <select
                        value={selectedArch}
                        onChange={e => {
                            setSelectedArch(e.target.value)
                            setResults({})
                            // Load node list
                            const arch = architectures.find(a => a.id === e.target.value)
                            if (arch) {
                                import('../api/client').then(mod => {
                                    mod.getGraph(e.target.value).then(r => {
                                        setSelectedGraph(r.data)
                                        if (r.data.nodes?.length > 0) {
                                            setSeedNode(r.data.nodes[0].short_id || r.data.nodes[0].id || '')
                                            if (r.data.nodes.length > 1) {
                                                setTargetNode(r.data.nodes[r.data.nodes.length - 1].short_id || r.data.nodes[r.data.nodes.length - 1].id || '')
                                            }
                                        }
                                    })
                                })
                            }
                        }}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
                    >
                        <option value="">Select architecture...</option>
                        {architectures.map(a => (
                            <option key={a.id} value={a.id}>
                                {a.name} ({a.total_services} services)
                            </option>
                        ))}
                    </select>
                </div>

                {/* Seed node */}
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Seed Node</label>
                    <select
                        value={seedNode}
                        onChange={e => setSeedNode(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
                    >
                        <option value="">(auto-select)</option>
                        {nodeList.map(n => (
                            <option key={n.id || n.short_id} value={n.short_id || n.id}>
                                {n.name} ({n.type})
                            </option>
                        ))}
                    </select>
                </div>

                {/* Target node */}
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Target Node (Path-Based)</label>
                    <select
                        value={targetNode}
                        onChange={e => setTargetNode(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
                    >
                        <option value="">(auto-select)</option>
                        {nodeList.map(n => (
                            <option key={n.id || n.short_id} value={n.short_id || n.id}>
                                {n.name} ({n.type})
                            </option>
                        ))}
                    </select>
                </div>

                {/* Params */}
                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Hops</label>
                        <input type="number" min={1} max={5} value={hops} onChange={e => setHops(+e.target.value)}
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Window (h)</label>
                        <input type="number" min={1} max={8760} value={windowHours} onChange={e => setWindowHours(+e.target.value)}
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
                    </div>
                </div>
            </div>

            {/* Strategy Cards */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {Object.entries(STRATEGY_META).map(([key, meta]) => {
                    const c = COLORS[meta.color]
                    const isActive = activeStrategy === key
                    const result = results[key]
                    const hasResult = result && !result.error
                    return (
                        <button
                            key={key}
                            onClick={() => setActiveStrategy(key)}
                            className={`
                                relative p-4 rounded-xl border-2 text-left transition-all
                                ${isActive ? `${c.border} ${c.bg} ring-2 ${c.ring}` : 'border-gray-100 bg-white hover:border-gray-200'}
                            `}
                        >
                            <div className="flex items-center gap-2 mb-2">
                                <meta.icon className={`w-5 h-5 ${isActive ? c.text : 'text-gray-400'}`} />
                                <span className={`text-sm font-semibold ${isActive ? c.text : 'text-gray-700'}`}>
                                    {meta.label}
                                </span>
                            </div>
                            <p className="text-xs text-gray-500 leading-relaxed">{meta.desc}</p>
                            {hasResult && (
                                <div className={`mt-2 text-xs font-medium ${c.badge} px-2 py-0.5 rounded-full inline-block`}>
                                    {result.node_count} nodes · {result.edge_count} edges
                                </div>
                            )}
                            {result?.error && (
                                <div className="mt-2 text-xs text-red-600 flex items-center gap-1">
                                    <AlertCircle className="w-3 h-3" />
                                    Error
                                </div>
                            )}
                        </button>
                    )
                })}
            </div>

            {/* Run Selected Strategy */}
            <div className="flex items-center gap-3 mb-6">
                <button
                    onClick={runStrategy}
                    disabled={!selectedArch || loading}
                    className={`
                        flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium
                        bg-gradient-to-r shadow transition
                        ${COLORS[STRATEGY_META[activeStrategy]?.color]?.text || 'text-gray-700'}
                        from-white to-gray-50 border border-gray-200 hover:border-gray-300
                        disabled:opacity-50
                    `}
                >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
                        (() => { const Icon = STRATEGY_META[activeStrategy]?.icon || Target; return <Icon className="w-4 h-4" /> })()
                    )}
                    Run {STRATEGY_META[activeStrategy]?.label}
                </button>
                {selectedGraph && (
                    <span className="text-xs text-gray-500">
                        Graph: {selectedGraph.architecture?.name} · {selectedGraph.nodes?.length} nodes · {selectedGraph.links?.length} edges
                    </span>
                )}
            </div>

            {/* Results */}
            <div className="space-y-4">
                {Object.entries(results).map(([key, result]) => {
                    if (key === '_combined') return null
                    const meta = STRATEGY_META[key]
                    if (!meta) return null
                    const c = COLORS[meta.color]
                    const isExpanded = expandedResult === key

                    return (
                        <div key={key} className={`rounded-xl border ${c.border} overflow-hidden`}>
                            {/* Header */}
                            <button
                                onClick={() => setExpandedResult(isExpanded ? null : key)}
                                className={`w-full flex items-center justify-between px-5 py-3 ${c.bg}`}
                            >
                                <div className="flex items-center gap-3">
                                    <meta.icon className={`w-4 h-4 ${c.text}`} />
                                    <span className={`text-sm font-semibold ${c.text}`}>{meta.label}</span>
                                    {result.error ? (
                                        <span className="text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded">Error</span>
                                    ) : (
                                        <span className={`text-xs ${c.badge} px-2 py-0.5 rounded-full`}>
                                            {result.node_count} nodes · {result.edge_count} edges
                                        </span>
                                    )}
                                </div>
                                {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                            </button>

                            {/* Body */}
                            {isExpanded && (
                                <div className="p-5 bg-white">
                                    {result.error ? (
                                        <div className="text-sm text-red-600">{result.error}</div>
                                    ) : (
                                        <div className="space-y-4">
                                            {/* Context */}
                                            <div>
                                                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">LLM Context</h4>
                                                <pre className="text-xs text-gray-700 bg-gray-50 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-72 overflow-y-auto">
                                                    {result.context}
                                                </pre>
                                            </div>

                                            {/* Nodes table */}
                                            {result.nodes?.length > 0 && (
                                                <div>
                                                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                                                        Nodes ({result.nodes.length})
                                                    </h4>
                                                    <div className="overflow-x-auto max-h-64 overflow-y-auto">
                                                        <table className="w-full text-xs">
                                                            <thead className="sticky top-0 bg-gray-50">
                                                                <tr className="text-left text-gray-500">
                                                                    <th className="px-3 py-2">Name</th>
                                                                    <th className="px-3 py-2">Type</th>
                                                                    <th className="px-3 py-2 text-right">Cost/mo</th>
                                                                    <th className="px-3 py-2 text-right">PageRank</th>
                                                                    <th className="px-3 py-2 text-right">Betweenness</th>
                                                                    <th className="px-3 py-2 text-right">In°</th>
                                                                    <th className="px-3 py-2 text-right">Out°</th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {result.nodes.map(n => (
                                                                    <tr key={n.id} className="border-t border-gray-100 hover:bg-gray-50">
                                                                        <td className="px-3 py-1.5 font-medium text-gray-800">{n.name}</td>
                                                                        <td className="px-3 py-1.5">
                                                                            <span className="px-1.5 py-0.5 rounded text-xs" style={{ backgroundColor: n.color + '22', color: n.color }}>
                                                                                {n.type}
                                                                            </span>
                                                                        </td>
                                                                        <td className="px-3 py-1.5 text-right">${(n.cost_monthly || 0).toFixed(0)}</td>
                                                                        <td className="px-3 py-1.5 text-right">{(n.pagerank || 0).toFixed(4)}</td>
                                                                        <td className="px-3 py-1.5 text-right">{(n.betweenness || 0).toFixed(4)}</td>
                                                                        <td className="px-3 py-1.5 text-right">{n.in_degree || 0}</td>
                                                                        <td className="px-3 py-1.5 text-right">{n.out_degree || 0}</td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Edges table */}
                                            {result.edges?.length > 0 && (
                                                <div>
                                                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                                                        Edges ({result.edges.length})
                                                    </h4>
                                                    <div className="overflow-x-auto max-h-48 overflow-y-auto">
                                                        <table className="w-full text-xs">
                                                            <thead className="sticky top-0 bg-gray-50">
                                                                <tr className="text-left text-gray-500">
                                                                    <th className="px-3 py-2">Source</th>
                                                                    <th className="px-3 py-2">→</th>
                                                                    <th className="px-3 py-2">Target</th>
                                                                    <th className="px-3 py-2">Type</th>
                                                                    <th className="px-3 py-2 text-right">Weight</th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {result.edges.map((e, i) => (
                                                                    <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                                                                        <td className="px-3 py-1.5 text-gray-700">{e.source}</td>
                                                                        <td className="px-3 py-1.5 text-gray-400">→</td>
                                                                        <td className="px-3 py-1.5 text-gray-700">{e.target}</td>
                                                                        <td className="px-3 py-1.5 text-gray-500">{e.type}</td>
                                                                        <td className="px-3 py-1.5 text-right">{(e.weight || 0).toFixed(2)}</td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Strategy-specific metadata */}
                                            {result.metadata && (
                                                <div>
                                                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Strategy Metadata</h4>
                                                    <pre className="text-xs text-gray-600 bg-gray-50 p-3 rounded-lg overflow-x-auto max-h-48 overflow-y-auto font-mono">
                                                        {JSON.stringify(result.metadata, null, 2)}
                                                    </pre>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}

                {/* Combined summary */}
                {results._combined && !results._combined.error && (
                    <div className="rounded-xl border-2 border-violet-200 overflow-hidden">
                        <div className="px-5 py-3 bg-violet-50 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Zap className="w-4 h-4 text-violet-600" />
                                <span className="text-sm font-semibold text-violet-700">Combined Traversal Summary</span>
                                <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full">
                                    {results._combined.total_nodes} unique nodes · {results._combined.total_edges} unique edges
                                </span>
                            </div>
                        </div>
                        <div className="p-5 bg-white">
                            <pre className="text-xs text-gray-700 bg-gray-50 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-96 overflow-y-auto">
                                {results._combined.merged_context}
                            </pre>
                        </div>
                    </div>
                )}
            </div>

            {/* Empty state */}
            {Object.keys(results).length === 0 && (
                <div className="text-center py-20 text-gray-400">
                    <Share2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">Select an architecture and run a traversal strategy</p>
                    <p className="text-xs mt-1">Choose from Ego Network, Path-Based, Cluster-Based, or Temporal expansion</p>
                </div>
            )}
        </div>
    )
}
