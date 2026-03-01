import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { listArchitectures, analyzeArchitecture } from '../api/client'
import {
    BrainCircuit, Sparkles, AlertTriangle, Shield, TrendingUp,
    DollarSign, Activity, Cpu, Zap, ChevronDown, Search,
    Target, Eye, BarChart3, FileText, ArrowRight,
    CheckCircle2, XCircle, Clock, Layers, GitBranch,
    Lightbulb, Wrench, ArrowUpRight
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════
   Severity color mapping (light theme)
 ═══════════════════════════════════════════════════════════════ */
const SEV = {
    critical: { bg: '#fef2f2', border: '#fecaca', text: '#991b1b', badge: 'bg-red-100 text-red-700', icon: XCircle },
    high: { bg: '#fffbeb', border: '#fde68a', text: '#92400e', badge: 'bg-amber-100 text-amber-700', icon: AlertTriangle },
    moderate: { bg: '#eff6ff', border: '#bfdbfe', text: '#1e40af', badge: 'bg-blue-100 text-blue-700', icon: Eye },
    low: { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534', badge: 'bg-emerald-100 text-emerald-700', icon: CheckCircle2 },
}

const AGENT_META = {
    topology_analyst: { color: '#4f46e5', icon: GitBranch, label: 'Topology' },
    behavior_scientist: { color: '#7c3aed', icon: Activity, label: 'Behavior' },
    cost_economist: { color: '#d97706', icon: DollarSign, label: 'Cost' },
    risk_detective: { color: '#e11d48', icon: Target, label: 'Detective' },
    executive_synthesizer: { color: '#0891b2', icon: BrainCircuit, label: 'Synthesizer' },
}

/* ═══════════════════════════════════════════════════════════════
   Risk Gauge — circular SVG, light bg
 ═══════════════════════════════════════════════════════════════ */
function RiskGauge({ score }) {
    const pct = Math.round(score * 100)
    const color = pct >= 70 ? '#dc2626' : pct >= 40 ? '#d97706' : '#16a34a'
    const circ = 2 * Math.PI * 56
    const off = circ - (pct / 100) * circ

    return (
        <div className="relative w-36 h-36 mx-auto flex-shrink-0">
            <svg viewBox="0 0 128 128" className="w-full h-full -rotate-90">
                <circle cx="64" cy="64" r="56" fill="none" stroke="#f3f4f6" strokeWidth="10" />
                <circle cx="64" cy="64" r="56" fill="none" stroke={color} strokeWidth="10"
                    strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
                    className="transition-all duration-1000 ease-out" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-black" style={{ color }}>{pct}%</span>
                <span className="text-[10px] text-gray-400 uppercase tracking-widest font-semibold mt-0.5">Risk Score</span>
            </div>
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Recommendation Card — super legible AWS-style
 ═══════════════════════════════════════════════════════════════ */
function RecommendationCard({ text, index }) {
    const themes = [
        { color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', icon: Shield, label: 'AWS Shield' },
        { color: '#059669', bg: '#f0fdf4', border: '#bbf7d0', icon: TrendingUp, label: 'Scaling' },
        { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: DollarSign, label: 'Cost Savings' },
        { color: '#e11d48', bg: '#fff1f2', border: '#fecdd3', icon: Target, label: 'Risk Mitigation' },
        { color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe', icon: Wrench, label: 'Architecture' },
        { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: Lightbulb, label: 'Optimization' },
    ]
    const t = themes[index % themes.length]
    const Icon = t.icon

    // Split the text into actionable sentences for readability
    const sentences = text.split(/(?<=\.)\s+/).filter(Boolean)

    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md hover:border-blue-200 hover:-translate-y-0.5">
            {/* Top accent bar */}
            <div className="h-1.5" style={{ backgroundColor: t.color }} />

            <div className="p-5">
                {/* Header */}
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ backgroundColor: t.bg, border: `1px solid ${t.border}` }}>
                        <Icon className="w-5 h-5" style={{ color: t.color }} />
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: t.color }}>
                            Recommendation #{index + 1}
                        </p>
                        <p className="text-xs text-gray-400">{t.label}</p>
                    </div>
                </div>

                {/* Content — broken into readable steps */}
                <div className="space-y-2.5">
                    {sentences.map((s, i) => (
                        <div key={i} className="flex items-start gap-2.5">
                            <div className="mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: t.color }} />
                            <p className="text-sm text-gray-700 leading-relaxed">{s.trim()}</p>
                        </div>
                    ))}
                </div>

                {/* Footer */}
                <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-gray-100">
                    <BrainCircuit className="w-3 h-3 text-gray-300" />
                    <span className="text-[10px] text-gray-400">Generated by FinOps-R1 AI (GraphRAG-grounded)</span>
                </div>
            </div>
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Finding Card — severity-colored, light theme
 ═══════════════════════════════════════════════════════════════ */
function FindingCard({ finding }) {
    const sev = SEV[finding.severity] || SEV.moderate
    const agent = AGENT_META[finding.source_agent] || { color: '#6b7280', icon: FileText, label: '?' }
    const SevIcon = sev.icon
    const AgentIcon = agent.icon

    return (
        <div className="rounded-xl p-4 border transition-all duration-200 hover:shadow-sm"
            style={{ backgroundColor: sev.bg, borderColor: sev.border }}>
            <div className="flex items-start gap-3">
                <SevIcon className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: sev.text }} />
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                        <span className={`badge ${sev.badge} text-[10px]`}>{finding.severity.toUpperCase()}</span>
                        <span className="text-[10px] flex items-center gap-1" style={{ color: agent.color }}>
                            <AgentIcon className="w-3 h-3" /> {agent.label}
                        </span>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: sev.text }}>{finding.description}</p>
                    {finding.affected_node && (
                        <p className="text-xs text-gray-400 mt-1.5">
                            Resource: <code className="text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded font-medium">{finding.affected_node}</code>
                        </p>
                    )}
                </div>
            </div>
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Agent Pipeline Progress
 ═══════════════════════════════════════════════════════════════ */
function AgentProgress({ agentResults, timings }) {
    const steps = [
        { key: 'topology_analyst', label: 'Infrastructure Topology' },
        { key: 'behavior_scientist', label: 'Behavior Analysis' },
        { key: 'cost_economist', label: 'Cost Economics' },
        { key: 'risk_detective', label: 'Root Cause Detective' },
        { key: 'executive_synthesizer', label: 'Executive Summary' },
    ]

    return (
        <div className="card p-5">
            <h3 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
                <BrainCircuit className="w-4 h-4 text-blue-600" />
                5-Agent Pipeline
            </h3>
            <div className="space-y-1.5">
                {steps.map(({ key, label }, i) => {
                    const meta = AGENT_META[key]
                    const Icon = meta.icon
                    const done = !!agentResults?.[key]
                    const ms = timings?.[key] || 0

                    return (
                        <div key={key} className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-50 transition-colors">
                            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold"
                                style={{ backgroundColor: meta.color + '12', color: meta.color }}>
                                {i + 1}
                            </div>
                            <Icon className="w-4 h-4" style={{ color: meta.color }} />
                            <span className="text-sm text-gray-600 flex-1">{label}</span>
                            {done ? (
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-gray-400">{ms}ms</span>
                                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                                </div>
                            ) : (
                                <div className="w-4 h-4 border-2 border-gray-200 rounded-full" />
                            )}
                        </div>
                    )
                })}
            </div>
            {timings?.total_ms && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
                    <span className="text-xs text-gray-400">Total pipeline</span>
                    <span className="text-xs font-bold text-blue-600 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {timings.total_ms}ms
                    </span>
                </div>
            )}
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Main Analysis Page
 ═══════════════════════════════════════════════════════════════ */
export default function AnalysisPage() {
    const location = useLocation()
    const [architectures, setArchitectures] = useState([])
    const [selectedArch, setSelectedArch] = useState(location.state?.arch || null)
    const [result, setResult] = useState(null)
    const [loading, setLoading] = useState(false)
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const [findingFilter, setFindingFilter] = useState('all')

    useEffect(() => {
        listArchitectures()
            .then(res => setArchitectures(res.data.architectures))
            .catch(() => { })
    }, [])

    useEffect(() => {
        if (selectedArch && !result) runAnalysis()
    }, [selectedArch])

    async function runAnalysis() {
        if (!selectedArch) return
        setLoading(true); setResult(null)
        try {
            const res = await analyzeArchitecture(selectedArch.filename)
            setResult(res.data)
        } catch (e) { console.error('Analysis failed:', e) }
        setLoading(false)
    }

    const filteredFindings = result?.all_findings?.filter(f =>
        findingFilter === 'all' || f.severity === findingFilter
    ) || []

    return (
        <div className="max-w-7xl mx-auto px-6 py-10">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                        <BrainCircuit className="w-7 h-7 text-blue-600" />
                        AI Cost Spike Prediction
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        GraphRAG-grounded • FinOps-R1 LLM • Zero hallucination pipeline
                    </p>
                </div>

                <div className="relative">
                    <button onClick={() => setDropdownOpen(!dropdownOpen)} className="btn-primary">
                        <Search className="w-4 h-4" />
                        {selectedArch?.name || 'Select Architecture'}
                        <ChevronDown className="w-4 h-4" />
                    </button>
                    {dropdownOpen && (
                        <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-30 max-h-72 overflow-y-auto">
                            {architectures.map(a => (
                                <button key={a.filename} onClick={() => { setSelectedArch(a); setDropdownOpen(false); setResult(null) }}
                                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors">
                                    <div className="flex justify-between items-center">
                                        <span className="font-medium">{a.name}</span>
                                        <span className="text-xs text-gray-400">{a.services} svcs • ${a.cost >= 1000 ? `${(a.cost / 1000).toFixed(0)}K` : a.cost}</span>
                                    </div>
                                    <span className="text-xs text-gray-400 capitalize">{a.pattern} • {a.complexity}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Loading */}
            {loading && (
                <div className="card p-16 flex flex-col items-center justify-center mb-8">
                    <div className="relative mb-6">
                        <div className="w-16 h-16 rounded-full border-4 border-blue-100 border-t-blue-600 animate-spin" />
                        <BrainCircuit className="w-7 h-7 text-blue-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                    </div>
                    <p className="text-gray-900 font-semibold mb-1">Running FinOps-R1 Analysis Pipeline</p>
                    <p className="text-sm text-gray-400 text-center max-w-md">
                        Monte Carlo simulation → 5-agent analysis → GraphRAG-grounded recommendations
                    </p>
                    <div className="mt-5 flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 rounded-full bg-violet-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="space-y-6 animate-fade-in-up">
                    {/* Verdict Banner */}
                    <div className="card overflow-hidden">
                        <div className="h-1.5 bg-gradient-to-r from-blue-600 via-indigo-600 to-violet-600" />
                        <div className="p-8 flex items-center gap-10">
                            <RiskGauge score={result.risk_score} />
                            <div className="flex-1">
                                <div className="flex items-center gap-2 mb-3">
                                    <Sparkles className="w-5 h-5 text-blue-600" />
                                    <h2 className="text-lg font-bold text-gray-900">Executive Verdict</h2>
                                </div>
                                <p className="text-sm text-gray-600 leading-relaxed mb-5">{result.verdict}</p>
                                <div className="grid grid-cols-3 gap-3">
                                    {[
                                        { label: 'Architecture', value: result.architecture },
                                        { label: 'Baseline Cost', value: `$${result.baseline_cost_monthly?.toLocaleString()}/mo` },
                                        { label: 'Total Findings', value: result.all_findings?.length || 0 },
                                    ].map(({ label, value }) => (
                                        <div key={label} className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                                            <p className="text-[10px] text-gray-400 uppercase mb-0.5">{label}</p>
                                            <p className="text-sm font-bold text-gray-900">{value}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Root Cause */}
                    {result.root_cause && (
                        <div className="card p-5 border-l-4 border-l-red-500 bg-red-50/30">
                            <div className="flex items-center gap-2 mb-2">
                                <Target className="w-5 h-5 text-red-600" />
                                <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider">Root Cause</h3>
                            </div>
                            <p className="text-sm text-gray-700 leading-relaxed">{result.root_cause}</p>
                        </div>
                    )}

                    {/* Two Column: Pipeline + Recommendations */}
                    <div className="grid grid-cols-3 gap-6">
                        <div>
                            <AgentProgress agentResults={result.agents} timings={result.timings} />
                        </div>
                        <div className="col-span-2">
                            <div className="flex items-center gap-2 mb-4">
                                <Sparkles className="w-5 h-5 text-violet-600" />
                                <h3 className="text-lg font-bold text-gray-900">AI-Generated AWS Recommendations</h3>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                {(result.recommendations || []).map((rec, i) => (
                                    <RecommendationCard key={i} text={rec} index={i} />
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Findings */}
                    <div>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                <BarChart3 className="w-5 h-5 text-amber-600" />
                                All Findings ({result.all_findings?.length || 0})
                            </h3>
                            <div className="flex gap-1.5">
                                {['all', 'critical', 'high', 'moderate', 'low'].map(f => (
                                    <button key={f} onClick={() => setFindingFilter(f)}
                                        className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${findingFilter === f
                                                ? 'bg-blue-600 text-white shadow-sm'
                                                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100 border border-transparent'
                                            }`}>
                                        {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                                        {f !== 'all' && <span className="ml-1 opacity-60">({result.all_findings?.filter(x => x.severity === f).length || 0})</span>}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            {filteredFindings.map((f, i) => <FindingCard key={i} finding={f} />)}
                        </div>
                    </div>
                </div>
            )}

            {/* Empty State */}
            {!loading && !result && !selectedArch && (
                <div className="card p-20 text-center">
                    <BrainCircuit className="w-16 h-16 text-gray-200 mx-auto mb-4" />
                    <h3 className="text-lg font-bold text-gray-400 mb-2">Select an AWS Architecture</h3>
                    <p className="text-sm text-gray-400 max-w-md mx-auto leading-relaxed">
                        Choose from the dropdown above or navigate from the Dashboard.
                        The FinOps-R1 LLM will analyze your architecture for hidden cost spike risks.
                    </p>
                </div>
            )}
        </div>
    )
}
