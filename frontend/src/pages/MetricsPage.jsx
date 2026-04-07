import { useState, useEffect } from 'react'
import {
    BarChart3, Activity, Zap, Server, GitBranch, ChevronDown,
    Loader2, AlertCircle, TrendingUp, Shield, Target, Layers,
    ArrowUpRight, ArrowDownRight, Minus, RefreshCw, DollarSign
} from 'lucide-react'
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
    RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
    Treemap, Cell, PieChart, Pie
} from 'recharts'
import { listGraphs, getGraph, getGraphMetrics } from '../api/client'

const COLORS = [
    '#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899',
    '#f43f5e', '#ef4444', '#f97316', '#f59e0b', '#eab308',
    '#84cc16', '#22c55e', '#10b981', '#14b8a6', '#06b6d4',
    '#0ea5e9', '#3b82f6', '#2563eb',
]

/* ───────── Metric card with trend icon ───────── */
function MetricCard({ label, value, subtitle, icon: Icon, color = 'blue', trend }) {
    return (
        <div className="card p-4 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-2">
                <div className={`w-9 h-9 rounded-lg bg-${color}-50 border border-${color}-100 flex items-center justify-center`}>
                    <Icon className={`w-4.5 h-4.5 text-${color}-600`} />
                </div>
                {trend === 'up' && <ArrowUpRight className="w-4 h-4 text-red-500" />}
                {trend === 'down' && <ArrowDownRight className="w-4 h-4 text-emerald-500" />}
                {trend === 'neutral' && <Minus className="w-4 h-4 text-gray-400" />}
            </div>
            <p className="text-xl font-bold text-gray-900">{value}</p>
            <p className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">{label}</p>
            {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
        </div>
    )
}

/* ───────── Ranking table ───────── */
function RankingTable({ title, icon: Icon, color, data, scoreLabel }) {
    if (!data || data.length === 0) return null
    return (
        <div className="card p-4">
            <div className="flex items-center gap-2 mb-3">
                <Icon className={`w-4 h-4 text-${color}-600`} />
                <h3 className="text-sm font-bold text-gray-900">{title}</h3>
            </div>
            <div className="space-y-2">
                {data.map(([node, score], i) => (
                    <div key={node} className="flex items-center gap-2">
                        <span className={`w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold
                            ${i === 0 ? `bg-${color}-100 text-${color}-700 ring-1 ring-${color}-300`
                                : i < 3 ? `bg-${color}-50 text-${color}-600`
                                    : 'bg-gray-50 text-gray-500'
                            }`}>
                            {i + 1}
                        </span>
                        <span className="text-xs text-gray-700 font-medium flex-1 truncate">{node}</span>
                        <div className="w-24">
                            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                    className={`h-full bg-${color}-500 rounded-full transition-all duration-500`}
                                    style={{ width: `${Math.min((score / (data[0]?.[1] || 1)) * 100, 100)}%` }}
                                />
                            </div>
                        </div>
                        <span className="text-[10px] text-gray-500 font-mono w-16 text-right">{typeof score === 'number' ? score.toFixed(4) : score}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

export default function MetricsPage() {
    const [graphs, setGraphs] = useState([])
    const [selectedGraph, setSelectedGraph] = useState(null)
    const [dropdown, setDropdown] = useState(false)
    const [loading, setLoading] = useState(false)
    const [metrics, setMetrics] = useState(null)
    const [graphData, setGraphData] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        listGraphs()
            .then(r => setGraphs(r.data.architectures || []))
            .catch(() => {})
    }, [])

    const selectArch = async (arch) => {
        setLoading(true)
        setDropdown(false)
        setSelectedGraph(arch)
        setError(null)
        try {
            const [graphRes, metricsRes] = await Promise.all([
                getGraph(arch.id),
                getGraphMetrics(arch.id),
            ])
            setGraphData(graphRes.data)
            setMetrics(metricsRes.data.metrics)
        } catch (err) {
            setError(err.response?.data?.detail || err.message)
        }
        setLoading(false)
    }

    // Derived chart data
    const centralityBarData = metrics?.centrality?.top_bottlenecks?.map(([node, score]) => ({
        name: node.length > 15 ? node.slice(0, 15) + '…' : node,
        betweenness: +(score * 100).toFixed(2),
    })) || []

    const pagerankBarData = metrics?.pagerank?.top_important?.map(([node, score]) => ({
        name: node.length > 15 ? node.slice(0, 15) + '…' : node,
        pagerank: +(score * 100).toFixed(2),
    })) || []

    const clusteringData = metrics?.clustering?.coefficients
        ? Object.entries(metrics.clustering.coefficients)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10)
            .map(([node, coeff]) => ({
                name: node.length > 12 ? node.slice(0, 12) + '…' : node,
                clustering: +(coeff * 100).toFixed(2),
            }))
        : []

    // Service type distribution from graph nodes
    const typeDistribution = graphData?.nodes
        ? Object.entries(
            graphData.nodes.reduce((acc, n) => {
                acc[n.type] = (acc[n.type] || 0) + 1
                return acc
            }, {})
        ).map(([type, count]) => ({ name: type, value: count }))
        : []

    // Radar chart: top-5 nodes comparing multiple metrics
    const radarData = (() => {
        if (!metrics?.centrality?.betweenness || !metrics?.pagerank?.scores) return []
        const bc = metrics.centrality.betweenness
        const pr = metrics.pagerank.scores
        const cl = metrics.clustering?.coefficients || {}
        const deg = metrics.centrality?.degree || {}
        // Combine top nodes from all three
        const allNodes = new Set([
            ...Object.entries(bc).sort(([, a], [, b]) => b - a).slice(0, 5).map(([n]) => n),
        ])
        return [...allNodes].map(node => ({
            node: node.length > 12 ? node.slice(0, 12) + '…' : node,
            Betweenness: +((bc[node] || 0) * 100).toFixed(1),
            PageRank: +((pr[node] || 0) * 100).toFixed(1),
            Clustering: +((cl[node] || 0) * 100).toFixed(1),
            Degree: +((deg[node] || 0) * 100).toFixed(1),
        }))
    })()

    return (
        <div className="max-w-7xl mx-auto px-6 py-10 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
                        <BarChart3 className="w-8 h-8 text-amber-600" />
                        Graph Metrics
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        Centrality, PageRank, and Clustering analysis for your architecture graphs
                    </p>
                </div>
                <div className="relative">
                    <button onClick={() => setDropdown(!dropdown)} className="btn-outline min-w-[240px] justify-between">
                        <span className="text-sm truncate">{selectedGraph?.name || 'Select Architecture'}</span>
                        <ChevronDown className="w-4 h-4" />
                    </button>
                    {dropdown && (
                        <div className="absolute right-0 mt-2 w-72 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-30 max-h-64 overflow-y-auto">
                            {graphs.map(g => (
                                <button key={g.id} onClick={() => selectArch(g)}
                                    className="w-full text-left px-3 py-2 rounded-lg text-sm text-gray-700 hover:bg-amber-50 hover:text-amber-700 transition-colors flex justify-between">
                                    <span className="truncate">{g.name}</span>
                                    <span className="text-xs text-gray-400 ml-2">{g.total_services} svc</span>
                                </button>
                            ))}
                            {graphs.length === 0 && (
                                <p className="text-xs text-gray-400 text-center py-4">No architectures ingested yet</p>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {loading && (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
                </div>
            )}

            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4" /> {error}
                </div>
            )}

            {!loading && !metrics && !error && (
                <div className="card p-16 flex flex-col items-center gap-4 text-gray-400">
                    <BarChart3 className="w-16 h-16" />
                    <p className="text-sm">Select an architecture to view its graph metrics</p>
                    <p className="text-xs">Centrality · PageRank · Clustering coefficient</p>
                </div>
            )}

            {metrics && !loading && (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                        <MetricCard label="Total Nodes" value={metrics.summary?.total_nodes || 0} icon={Server} color="blue" />
                        <MetricCard label="Total Edges" value={metrics.summary?.total_edges || 0} icon={GitBranch} color="violet" />
                        <MetricCard label="Density" value={(metrics.summary?.density || 0).toFixed(4)} icon={Layers} color="indigo" />
                        <MetricCard label="Components" value={metrics.summary?.components || 0} icon={Target} color="teal" />
                        <MetricCard label="DAG" value={metrics.summary?.is_dag ? 'Yes' : 'No'} icon={Shield} color={metrics.summary?.is_dag ? 'emerald' : 'amber'} />
                        <MetricCard
                            label="Avg Clustering"
                            value={(metrics.summary?.avg_clustering || 0).toFixed(4)}
                            icon={TrendingUp}
                            color="orange"
                        />
                    </div>

                    {/* Top Rankings Row */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <RankingTable
                            title="Bottlenecks (Betweenness Centrality)"
                            icon={Activity}
                            color="orange"
                            data={metrics.centrality?.top_bottlenecks}
                            scoreLabel="Betweenness"
                        />
                        <RankingTable
                            title="Most Important (PageRank)"
                            icon={Zap}
                            color="blue"
                            data={metrics.pagerank?.top_important}
                            scoreLabel="PageRank"
                        />
                        <div className="card p-4">
                            <div className="flex items-center gap-2 mb-3">
                                <Server className="w-4 h-4 text-emerald-600" />
                                <h3 className="text-sm font-bold text-gray-900">Top Clustering Coefficients</h3>
                            </div>
                            {clusteringData.length > 0 ? (
                                <div className="space-y-2">
                                    {Object.entries(metrics.clustering.coefficients)
                                        .sort(([, a], [, b]) => b - a)
                                        .slice(0, 5)
                                        .map(([node, coeff], i) => (
                                        <div key={node} className="flex items-center gap-2">
                                            <span className={`w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold
                                                ${i === 0 ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300'
                                                    : i < 3 ? 'bg-emerald-50 text-emerald-600'
                                                        : 'bg-gray-50 text-gray-500'
                                                }`}>
                                                {i + 1}
                                            </span>
                                            <span className="text-xs text-gray-700 font-medium flex-1 truncate">{node}</span>
                                            <div className="w-24">
                                                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${coeff * 100}%` }} />
                                                </div>
                                            </div>
                                            <span className="text-[10px] text-gray-500 font-mono w-16 text-right">{coeff.toFixed(4)}</span>
                                        </div>
                                    ))}
                                </div>
                            ) : <p className="text-xs text-gray-400">No clustering data</p>}
                        </div>
                    </div>

                    {/* Charts Row */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* Betweenness Centrality Bar Chart */}
                        <div className="card p-5">
                            <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <Activity className="w-4 h-4 text-orange-600" />
                                Betweenness Centrality (Top 5)
                            </h3>
                            <p className="text-xs text-gray-400 mb-4">Higher = more traffic passes through this node → bottleneck risk</p>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart data={centralityBarData} layout="vertical" margin={{ left: 0, right: 20 }}>
                                    <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                                    <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                                    <Tooltip formatter={v => `${v}%`} />
                                    <Bar dataKey="betweenness" fill="#f97316" radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* PageRank Bar Chart */}
                        <div className="card p-5">
                            <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <Zap className="w-4 h-4 text-blue-600" />
                                PageRank Score (Top 5)
                            </h3>
                            <p className="text-xs text-gray-400 mb-4">Higher = recursively more important based on who depends on them</p>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart data={pagerankBarData} layout="vertical" margin={{ left: 0, right: 20 }}>
                                    <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                                    <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                                    <Tooltip formatter={v => `${v}%`} />
                                    <Bar dataKey="pagerank" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* Clustering Coefficient Bar Chart */}
                        <div className="card p-5">
                            <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <Server className="w-4 h-4 text-emerald-600" />
                                Clustering Coefficient (Top 10)
                            </h3>
                            <p className="text-xs text-gray-400 mb-4">Higher = neighbours of this node are tightly interconnected</p>
                            <ResponsiveContainer width="100%" height={250}>
                                <BarChart data={clusteringData} layout="vertical" margin={{ left: 0, right: 20 }}>
                                    <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                                    <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10 }} />
                                    <Tooltip formatter={v => `${v}%`} />
                                    <Bar dataKey="clustering" fill="#10b981" radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Radar Chart — Multi-metric comparison */}
                        {radarData.length > 0 && (
                            <div className="card p-5">
                                <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                    <Target className="w-4 h-4 text-indigo-600" />
                                    Multi-Metric Radar (Top 5 Nodes)
                                </h3>
                                <p className="text-xs text-gray-400 mb-4">Compare centrality, PageRank, clustering, and degree for key nodes</p>
                                <ResponsiveContainer width="100%" height={250}>
                                    <RadarChart data={radarData}>
                                        <PolarGrid stroke="#e5e7eb" />
                                        <PolarAngleAxis dataKey="node" tick={{ fontSize: 9 }} />
                                        <PolarRadiusAxis tick={{ fontSize: 8 }} />
                                        <Radar name="Betweenness" dataKey="Betweenness" stroke="#f97316" fill="#f97316" fillOpacity={0.15} />
                                        <Radar name="PageRank" dataKey="PageRank" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} />
                                        <Radar name="Clustering" dataKey="Clustering" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                                        <Radar name="Degree" dataKey="Degree" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.15} />
                                        <Tooltip />
                                    </RadarChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </div>

                    {/* Service Type Distribution */}
                    {typeDistribution.length > 0 && (
                        <div className="card p-5">
                            <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <Layers className="w-4 h-4 text-violet-600" />
                                Service Type Distribution
                            </h3>
                            <p className="text-xs text-gray-400 mb-4">Breakdown of node types in this architecture</p>
                            <div className="flex items-center gap-8">
                                <ResponsiveContainer width={200} height={200}>
                                    <PieChart>
                                        <Pie
                                            data={typeDistribution}
                                            cx="50%"
                                            cy="50%"
                                            outerRadius={80}
                                            innerRadius={40}
                                            dataKey="value"
                                            paddingAngle={2}
                                        >
                                            {typeDistribution.map((_, i) => (
                                                <Cell key={i} fill={COLORS[i % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip />
                                    </PieChart>
                                </ResponsiveContainer>
                                <div className="flex flex-wrap gap-3">
                                    {typeDistribution.map((entry, i) => (
                                        <div key={entry.name} className="flex items-center gap-2">
                                            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                                            <span className="text-xs text-gray-600 capitalize">{entry.name.replace('_', ' ')}</span>
                                            <span className="text-xs font-bold text-gray-900">{entry.value}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Interpretation Guide */}
                    <div className="card p-5 bg-gradient-to-r from-gray-50 to-blue-50/30">
                        <h3 className="text-sm font-bold text-gray-900 mb-3">How to Read These Metrics</h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="p-3 bg-white rounded-lg border border-orange-100">
                                <div className="flex items-center gap-2 mb-2">
                                    <Activity className="w-4 h-4 text-orange-600" />
                                    <span className="text-xs font-bold text-orange-700">Centrality</span>
                                </div>
                                <p className="text-xs text-gray-600 leading-relaxed">
                                    <strong>Betweenness centrality</strong> measures how often a node sits on the shortest path between other nodes.
                                    High betweenness = <strong>bottleneck risk</strong>. If this service fails, many others lose connectivity.
                                    Consider adding redundancy or load balancing.
                                </p>
                            </div>
                            <div className="p-3 bg-white rounded-lg border border-blue-100">
                                <div className="flex items-center gap-2 mb-2">
                                    <Zap className="w-4 h-4 text-blue-600" />
                                    <span className="text-xs font-bold text-blue-700">PageRank</span>
                                </div>
                                <p className="text-xs text-gray-600 leading-relaxed">
                                    <strong>PageRank</strong> scores recursive importance — a node is important if important nodes depend on it.
                                    High PageRank = <strong>business-critical service</strong>. Prioritize monitoring, auto-scaling, and disaster recovery.
                                </p>
                            </div>
                            <div className="p-3 bg-white rounded-lg border border-emerald-100">
                                <div className="flex items-center gap-2 mb-2">
                                    <Server className="w-4 h-4 text-emerald-600" />
                                    <span className="text-xs font-bold text-emerald-700">Clustering</span>
                                </div>
                                <p className="text-xs text-gray-600 leading-relaxed">
                                    <strong>Clustering coefficient</strong> measures how interconnected a node's neighbours are.
                                    High clustering = <strong>tightly coupled cluster</strong>. A failure can cascade through the cluster.
                                    Consider circuit breakers and bulkhead patterns.
                                </p>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
