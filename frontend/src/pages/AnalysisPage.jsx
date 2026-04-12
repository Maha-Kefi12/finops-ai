import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
    listArchitectures, analyzeArchitecture, ingestFromAws,
    getAwsPipelineStatus, deepGraphAnalysis, generateRecommendations,
    getLastRecommendations, getRecommendationsHistory, 
    getLatestLLMReport, getLLMReportHistory,
} from '../api/client'
import { RecommendationCarousel } from '../components/StyledRecommendationCard'
import {
    BrainCircuit, Sparkles, AlertTriangle, Shield, TrendingUp,
    DollarSign, Activity, Cpu, Zap, ChevronDown, Search,
    Target, Eye, BarChart3, FileText, ArrowRight,
    CheckCircle2, XCircle, Clock, Layers, GitBranch,
    Lightbulb, Wrench, ArrowUpRight, Cloud, Loader2,
    Network, Database, Server, ChevronUp, AlertCircle,
    Hash, Gauge, Box, ArrowDown, Code, BarChart2,
    CircleDot, TrendingDown, Flame, HardDrive, Workflow, BookOpen, History, Settings
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════
   Constants
 ═══════════════════════════════════════════════════════════════ */
const AWS_STAGES = [
    { key: 'queued', label: 'Queued', icon: Clock, pct: 5 },
    { key: 'discovery', label: 'Discovery', icon: Search, pct: 20 },
    { key: 'graph_build', label: 'Graph', icon: Network, pct: 35 },
    { key: 'security_scan', label: 'Security', icon: Shield, pct: 50 },
    { key: 'neo4j_store', label: 'Storage', icon: Database, pct: 65 },
    { key: 'llm_report', label: 'LLM Report', icon: BrainCircuit, pct: 85 },
    { key: 'completed', label: 'Done', icon: CheckCircle2, pct: 100 },
]

function stagePct(stage) {
    if (stage === 'failed') return 0
    const norm = stage
        ?.replace(/_done$/, '')
        .replace(/^stored$/, 'neo4j_store')
        .replace(/^graph_done$/, 'graph_build')
        .replace(/^security_done$/, 'security_scan')
        .replace(/^neo4j_done$/, 'neo4j_store')
        .replace(/^llm_done$/, 'llm_report')
        || 'queued'
    return AWS_STAGES.find(s => s.key === norm)?.pct || 10
}

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

const CASCADE_COLORS = {
    critical: 'text-red-700 bg-red-50 border-red-200',
    high: 'text-orange-700 bg-orange-50 border-orange-200',
    moderate: 'text-amber-700 bg-amber-50 border-amber-200',
    low: 'text-emerald-700 bg-emerald-50 border-emerald-200',
}

const RISK_COLORS = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-amber-500',
    low: 'bg-emerald-500',
}

/* ═══════════════════════════════════════════════════════════════
   Shared Components
 ═══════════════════════════════════════════════════════════════ */
function MetricPill({ label, value, color = 'blue', small = false }) {
    return (
        <div className={`px-2.5 py-1.5 rounded-lg bg-${color}-50 border border-${color}-100`}>
            <p className={`${small ? 'text-[8px]' : 'text-[10px]'} text-gray-400 uppercase`}>{label}</p>
            <p className={`${small ? 'text-xs' : 'text-sm'} font-bold text-${color}-700`}>{value}</p>
        </div>
    )
}

/* ── AWS Progress Bar ──────────────────────────────────────── */
function AwsProgressBar({ progress, onCancel }) {
    if (!progress) return null
    const { stage, detail, elapsed, totalServices, totalCost, error } = progress
    const isDone = stage === 'completed'
    const isFailed = stage === 'failed'
    const pct = isDone ? 100 : isFailed ? 0 : stagePct(stage)
    return (
        <div className="card p-5 mb-6 border-2 border-amber-200 bg-gradient-to-br from-amber-50/50 to-orange-50/50">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    {isDone ? <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        : isFailed ? <XCircle className="w-5 h-5 text-red-600" />
                            : <Loader2 className="w-5 h-5 text-amber-600 animate-spin" />}
                    <span className={`text-sm font-bold ${isDone ? 'text-emerald-700' : isFailed ? 'text-red-700' : 'text-amber-700'}`}>
                        {isDone ? 'AWS Ingestion Complete — Running Analysis...' : isFailed ? 'Ingestion Failed' : 'AWS Live Discovery'}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    {elapsed > 0 && <span className="text-xs text-gray-500 font-mono bg-white px-2 py-1 rounded border border-gray-200">{elapsed.toFixed(1)}s</span>}
                    {!isDone && !isFailed && onCancel && <button onClick={onCancel} className="text-xs text-gray-400 hover:text-gray-600">Cancel</button>}
                </div>
            </div>
            <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden mb-2">
                <div className={`h-full rounded-full transition-all duration-700 ease-out ${isDone ? 'bg-emerald-500' : isFailed ? 'bg-red-500' : 'bg-gradient-to-r from-amber-400 to-orange-500'}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="flex items-center justify-between mb-2">
                {AWS_STAGES.map(s => {
                    const Icon = s.icon; const currentPct = stagePct(stage)
                    const isActive = !isFailed && Math.abs(currentPct - s.pct) < 15 && currentPct <= s.pct
                    const isComplete = !isFailed && currentPct > s.pct
                    return (
                        <div key={s.key} className="flex flex-col items-center gap-1">
                            <div className={`w-7 h-7 rounded-full flex items-center justify-center transition-all duration-300 ${isComplete ? 'bg-emerald-100 text-emerald-600 border border-emerald-300' : isActive ? 'bg-amber-100 text-amber-700 border border-amber-400 ring-2 ring-amber-200' : 'bg-gray-100 text-gray-400 border border-gray-200'}`}>
                                {isComplete ? <CheckCircle2 className="w-3.5 h-3.5" /> : isActive ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                            </div>
                            <span className={`text-[9px] font-medium ${isActive ? 'text-amber-700' : isComplete ? 'text-emerald-600' : 'text-gray-400'}`}>{s.label}</span>
                        </div>
                    )
                })}
            </div>
            {detail && <div className={`rounded-lg px-3 py-2 text-xs flex items-center gap-2 ${isFailed ? 'bg-red-50 text-red-700 border border-red-200' : isDone ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-white text-gray-600 border border-gray-200'}`}>{!isDone && !isFailed && <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />}{detail}</div>}
            {isDone && totalServices > 0 && <div className="grid grid-cols-2 gap-3 mt-3"><div className="bg-white rounded-lg p-2.5 border border-emerald-200 shadow-sm"><p className="text-xs text-gray-500 flex items-center gap-1"><Server className="w-3 h-3" /> Resources</p><p className="text-base font-bold text-gray-900">{totalServices}</p></div><div className="bg-white rounded-lg p-2.5 border border-emerald-200 shadow-sm"><p className="text-xs text-gray-500 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Monthly Cost</p><p className="text-base font-bold text-gray-900">${(totalCost || 0).toLocaleString()}</p></div></div>}
            {isFailed && error && <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3"><p className="text-xs text-red-600 font-mono break-all">{error}</p></div>}
        </div>
    )
}

/* ── Risk Gauge ──────────────────────────────────────────── */
function RiskGauge({ score }) {
    const pct = Math.round(score * 100)
    const color = pct >= 70 ? '#dc2626' : pct >= 40 ? '#d97706' : '#16a34a'
    const circ = 2 * Math.PI * 56; const off = circ - (pct / 100) * circ
    return (
        <div className="relative w-36 h-36 mx-auto flex-shrink-0">
            <svg viewBox="0 0 128 128" className="w-full h-full -rotate-90">
                <circle cx="64" cy="64" r="56" fill="none" stroke="#f3f4f6" strokeWidth="10" />
                <circle cx="64" cy="64" r="56" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off} className="transition-all duration-1000 ease-out" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-black" style={{ color }}>{pct}%</span>
                <span className="text-[10px] text-gray-400 uppercase tracking-widest font-semibold mt-0.5">Risk Score</span>
            </div>
        </div>
    )
}

/* ── Recommendation Card ─────────────────────────────────── */
function RecommendationCard({ text, index }) {
    const themes = [
        { color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', icon: Shield, label: 'AWS Shield' },
        { color: '#059669', bg: '#f0fdf4', border: '#bbf7d0', icon: TrendingUp, label: 'Scaling' },
        { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: DollarSign, label: 'Cost Savings' },
        { color: '#e11d48', bg: '#fff1f2', border: '#fecdd3', icon: Target, label: 'Risk Mitigation' },
        { color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe', icon: Wrench, label: 'Architecture' },
        { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: Lightbulb, label: 'Optimization' },
    ]
    const t = themes[index % themes.length]; const Icon = t.icon
    const sentences = text.split(/(?<=\.)\s+/).filter(Boolean)
    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md hover:border-blue-200 hover:-translate-y-0.5">
            <div className="h-1.5" style={{ backgroundColor: t.color }} />
            <div className="p-5">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: t.bg, border: `1px solid ${t.border}` }}>
                        <Icon className="w-5 h-5" style={{ color: t.color }} />
                    </div>
                    <div><p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: t.color }}>Recommendation #{index + 1}</p><p className="text-xs text-gray-400">{t.label}</p></div>
                </div>
                <div className="space-y-2.5">{sentences.map((s, i) => (<div key={i} className="flex items-start gap-2.5"><div className="mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: t.color }} /><p className="text-sm text-gray-700 leading-relaxed">{s.trim()}</p></div>))}</div>
                <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-gray-100"><BrainCircuit className="w-3 h-3 text-gray-300" /><span className="text-[10px] text-gray-400">Generated by FinOps-R1 AI (GraphRAG-grounded)</span></div>
            </div>
        </div>
    )
}

/* ── Display text sanitizer (no LaTeX/symbols) ───────────── */
function cleanDisplayText(str) {
    if (str == null || typeof str !== 'string') return ''
    let t = str

    // 1. Remove markdown headers (###, ##, #) but keep the text
    t = t.replace(/^#+\s*/gm, '')

    // 2. Remove LaTeX/math symbols but KEEP the content
    t = t.replace(/\\text\s*\{([^}]*)\}/g, '$1')
    t = t.replace(/\\times\s*/g, ' × ').replace(/\\cdot\s*/g, ' ')
    t = t.replace(/\\\$/g, '$').replace(/\\,/g, ' ')

    // 3. Remove LaTeX delimiters
    t = t.replace(/\\\(|\\\)|\\\[|\\\]/g, '')

    // 4. Remove Markdown bold/italic
    t = t.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1')
    t = t.replace(/`([^`]+)`/g, '$1')

    // 5. Clean up whitespace but PRESERVE newlines
    // Replace 2+ spaces with single space, but leave \n alone
    t = t.replace(/[ \t]{2,}/g, ' ')

    // 6. Remove internal prompt artifacts that can leak into rendered cards.
    t = t.replace(/^\s*ENGINE\s*SIGNAL\s*#\d+\s*:.*$/gim, '')
    t = t.replace(/^\s*PRE-ANALYZED\s+RECOMMENDATIONS.*$/gim, '')
    t = t.replace(/^\s*#\s*signal\s*\d+.*$/gim, '')
    t = t.replace(/^\s*Signal\s*#\d+\s*:.*$/gim, '')

    // 7. Normalize extra blank lines introduced by stripping artifacts.
    t = t.replace(/\n{3,}/g, '\n\n')

    return t.trim()
}

/* ── Full Recommendation Card (with CUR breakdowns) ──────── */
const CATEGORY_THEMES = {
    'right-sizing': { color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', icon: Cpu, label: 'Right-Sizing' },
    'waste-elimination': { color: '#059669', bg: '#f0fdf4', border: '#bbf7d0', icon: TrendingDown, label: 'Waste Elimination' },
    'architecture': { color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe', icon: Workflow, label: 'Architecture' },
    'caching': { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: Database, label: 'Caching' },
    'reserved-capacity': { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: DollarSign, label: 'Reserved Capacity' },
    'networking': { color: '#e11d48', bg: '#fff1f2', border: '#fecdd3', icon: Network, label: 'Networking' },
    'security': { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: Shield, label: 'Security' },
    'reliability': { color: '#0d9488', bg: '#f0fdfa', border: '#99f6e4', icon: Activity, label: 'Reliability' },
    'performance': { color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe', icon: Zap, label: 'Performance' },
    'network-optimization': { color: '#e11d48', bg: '#fff1f2', border: '#fecdd3', icon: Network, label: 'Network Optimization' },
    'storage-optimization': { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: Database, label: 'Storage Optimization' },
    'configuration': { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: Settings, label: 'Configuration' },
}

const SEVERITY_BADGE = {
    critical: 'bg-red-100 text-red-700 border-red-200',
    high: 'bg-amber-100 text-amber-700 border-amber-200',
    medium: 'bg-blue-100 text-blue-700 border-blue-200',
    low: 'bg-emerald-100 text-emerald-700 border-emerald-200',
}

const COMPLEXITY_BADGE = {
    low: 'bg-emerald-50 text-emerald-600',
    medium: 'bg-amber-50 text-amber-600',
    high: 'bg-red-50 text-red-600',
}

function FullRecommendationCard({ card, index, isExpanded, onToggle }) {
    const theme = CATEGORY_THEMES[card.category] || CATEGORY_THEMES['right-sizing']
    const Icon = theme.icon
    const res = card.resource_identification || {}
    const cost = card.cost_breakdown || {}
    const lineItems = cost.line_items || []
    const inefficiencies = card.inefficiencies || []
    const recommendations = card.recommendations || []
    const sevClass = SEVERITY_BADGE[card.severity] || SEVERITY_BADGE.medium
    const complexClass = COMPLEXITY_BADGE[card.implementation_complexity] || COMPLEXITY_BADGE.medium
    const titleDisplay = cleanDisplayText(card.title)

    return (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-lg overflow-hidden transition-all duration-300 hover:shadow-xl hover:border-gray-200">
            {/* Accent bar */}
            <div className="h-1 w-full" style={{ background: `linear-gradient(90deg, ${theme.color}, ${theme.color}99, ${theme.color}44)` }} />

            {/* Header */}
            <div className="p-6 cursor-pointer" onClick={onToggle}>
                <div className="flex items-start gap-5">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-sm" style={{ backgroundColor: theme.bg, border: `1px solid ${theme.border}` }}>
                        <Icon className="w-6 h-6" style={{ color: theme.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                            <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${sevClass}`}>
                                {(card.severity || 'medium').toUpperCase()}
                            </span>
                            <span className="text-[10px] font-semibold px-2.5 py-1 rounded-full" style={{ backgroundColor: theme.bg, color: theme.color }}>
                                {theme.label}
                            </span>
                            <span className={`text-[10px] font-medium px-2.5 py-1 rounded-full ${complexClass}`}>
                                {(card.implementation_complexity || 'medium').toUpperCase()} COMPLEXITY
                            </span>
                        </div>
                        <h4 className="text-lg font-bold text-gray-900 mb-2 tracking-tight">{titleDisplay}</h4>
                        <div className="flex items-center gap-4 text-sm text-gray-500">
                            {res.service_name && <span className="flex items-center gap-1.5"><Server className="w-3.5 h-3.5" />{cleanDisplayText(res.service_name)}</span>}
                            {res.service_type && <span className="flex items-center gap-1.5"><Box className="w-3.5 h-3.5" />{cleanDisplayText(res.service_type)}</span>}
                            {res.region && <span className="flex items-center gap-1.5"><Cloud className="w-3.5 h-3.5" />{res.region}</span>}
                        </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                        {card.total_estimated_savings > 0 ? (
                            <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-2.5">
                                <p className="text-[10px] text-emerald-600 uppercase font-semibold tracking-wider">Savings</p>
                                <p className="text-2xl font-black text-emerald-700">
                                    ${card.total_estimated_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </p>
                                <p className="text-[10px] text-emerald-600">per month</p>
                            </div>
                        ) : (
                            <div className="bg-slate-50 border border-slate-100 rounded-xl px-4 py-2.5">
                                <p className="text-[10px] text-slate-500 uppercase font-semibold">Type</p>
                                <p className="text-sm font-bold text-slate-700">Reliability</p>
                            </div>
                        )}
                        <div className="mt-3 flex justify-end">
                            {isExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                        </div>
                    </div>
                </div>
            </div>

            {/* Expanded details */}
            {isExpanded && (
                <div className="border-t border-gray-100 bg-gradient-to-b from-gray-50/50 to-white">

                    {/* ━━━ GRAPH CONTEXT: Business Impact ━━━ */}
                    {card.graph_context && (card.graph_context.dependency_count > 0 || card.graph_context.blast_radius_pct > 0 || card.graph_context.narrative) && (
                        <div className="px-6 py-5">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-4 flex items-center gap-2">
                                <Target className="w-4 h-4 text-red-500" /> Why This Matters — Business Impact
                            </h5>

                            {/* Narrative (the graph-analyzer's rich description) */}
                            {card.graph_context.narrative && (
                                <div className="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-100 rounded-xl p-5 mb-4 shadow-sm">
                                    <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                                        {cleanDisplayText(card.graph_context.narrative)}
                                    </p>
                                </div>
                            )}

                            {/* Stats row: Blast Radius + Dependency Count + Cascade Risk */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                                {card.graph_context.blast_radius_pct > 0 && (
                                    <div className={`rounded-xl p-4 border ${card.graph_context.blast_radius_pct > 50 ? 'bg-red-50 border-red-200' : card.graph_context.blast_radius_pct > 25 ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-200'}`}>
                                        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">Blast Radius</p>
                                        <p className={`text-2xl font-black ${card.graph_context.blast_radius_pct > 50 ? 'text-red-600' : card.graph_context.blast_radius_pct > 25 ? 'text-amber-600' : 'text-gray-700'}`}>
                                            {card.graph_context.blast_radius_pct}%
                                        </p>
                                        <p className="text-[10px] text-gray-500">{card.graph_context.blast_radius_services} services affected</p>
                                    </div>
                                )}
                                {card.graph_context.dependency_count > 0 && (
                                    <div className="rounded-xl p-4 bg-blue-50 border border-blue-200">
                                        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">Depends On It</p>
                                        <p className="text-2xl font-black text-blue-700">{card.graph_context.dependency_count}</p>
                                        <p className="text-[10px] text-gray-500">upstream services</p>
                                    </div>
                                )}
                                {card.graph_context.centrality > 0 && (
                                    <div className="rounded-xl p-4 bg-violet-50 border border-violet-200">
                                        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">Centrality</p>
                                        <p className="text-2xl font-black text-violet-700">{card.graph_context.centrality.toFixed(4)}</p>
                                        <p className="text-[10px] text-gray-500">{card.graph_context.severity_label || 'architectural importance'}</p>
                                    </div>
                                )}
                                {card.graph_context.depends_on_count > 0 && (
                                    <div className="rounded-xl p-4 bg-slate-50 border border-slate-200">
                                        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">Depends On</p>
                                        <p className="text-2xl font-black text-slate-700">{card.graph_context.depends_on_count}</p>
                                        <p className="text-[10px] text-gray-500">downstream deps</p>
                                    </div>
                                )}
                            </div>

                            {/* Alert badges: SPOF + Cascade + Cross-AZ */}
                            <div className="flex flex-wrap gap-2 mb-4">
                                {card.graph_context.is_spof && (
                                    <span className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full bg-red-100 text-red-700 border border-red-300">
                                        <AlertTriangle className="w-3.5 h-3.5" /> SINGLE POINT OF FAILURE
                                    </span>
                                )}
                                {(card.graph_context.cascading_failure_risk === 'critical' || card.graph_context.cascading_failure_risk === 'high') && (
                                    <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full border ${card.graph_context.cascading_failure_risk === 'critical' ? 'bg-red-100 text-red-700 border-red-300' : 'bg-amber-100 text-amber-700 border-amber-300'}`}>
                                        <Zap className="w-3.5 h-3.5" /> CASCADE RISK: {card.graph_context.cascading_failure_risk.toUpperCase()}
                                    </span>
                                )}
                                {card.graph_context.cross_az_count > 0 && (
                                    <span className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full bg-orange-100 text-orange-700 border border-orange-300">
                                        <Cloud className="w-3.5 h-3.5" /> {card.graph_context.cross_az_count} CROSS-AZ DEPS (extra transfer costs)
                                    </span>
                                )}
                            </div>

                            {/* Dependent services tree */}
                            {card.graph_context.dependent_services?.length > 0 && (
                                <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
                                    <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-2">Services that depend on this resource:</p>
                                    <div className="flex flex-wrap gap-2">
                                        {card.graph_context.dependent_services.map((svc, i) => (
                                            <span key={i} className="text-xs bg-blue-50 text-blue-700 px-3 py-1.5 rounded-full border border-blue-200 font-medium">
                                                {svc}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Cross-AZ dependency details */}
                            {card.graph_context.cross_az_dependencies?.length > 0 && (
                                <div className="mt-3 bg-orange-50 rounded-xl p-4 border border-orange-100">
                                    <p className="text-[10px] font-bold text-orange-700 uppercase tracking-wider mb-2">Cross-AZ Dependencies (generating transfer costs):</p>
                                    <div className="flex flex-wrap gap-2">
                                        {card.graph_context.cross_az_dependencies.map((svc, i) => (
                                            <span key={i} className="text-xs bg-orange-100 text-orange-800 px-3 py-1.5 rounded-full border border-orange-200 font-medium">
                                                {svc}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Resource Identification */}
                    {res.current_config && (
                        <div className="px-6 py-4">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <Server className="w-3.5 h-3.5 text-gray-400" /> Resource Identification
                            </h5>
                            <div className="bg-white rounded-xl p-4 text-sm text-gray-700 border border-gray-100 shadow-sm">
                                {cleanDisplayText(res.current_config)}
                            </div>
                            {res.tags && Object.keys(res.tags).length > 0 && (
                                <div className="flex gap-2 mt-2 flex-wrap">
                                    {Object.entries(res.tags).map(([k, v]) => (
                                        <span key={k} className="text-[10px] bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full border border-gray-200">
                                            {k}: {String(v)}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* CUR Cost Breakdown */}
                    {lineItems.length > 0 && (
                        <div className="px-6 py-4">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <DollarSign className="w-3.5 h-3.5 text-gray-400" /> CUR Cost Breakdown
                            </h5>
                            <div className="overflow-hidden rounded-xl border border-gray-200 shadow-sm">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-gray-50">
                                            <th className="text-left px-4 py-3 text-[10px] font-bold text-gray-500 uppercase">Line Item</th>
                                            <th className="text-right px-4 py-3 text-[10px] font-bold text-gray-500 uppercase">Usage</th>
                                            <th className="text-right px-4 py-3 text-[10px] font-bold text-gray-500 uppercase">Cost</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 bg-white">
                                        {lineItems.map((li, i) => (
                                            <tr key={i} className="hover:bg-gray-50/80">
                                                <td className="px-4 py-3 text-gray-700 font-medium">{cleanDisplayText(li.item)}</td>
                                                <td className="px-4 py-3 text-gray-500 text-right font-mono text-xs">{li.usage}</td>
                                                <td className="px-4 py-3 text-gray-900 text-right font-bold">${(li.cost || 0).toFixed(2)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot>
                                        <tr className="bg-gray-50 font-bold">
                                            <td className="px-4 py-3 text-gray-700" colSpan={2}>Total Monthly</td>
                                            <td className="px-4 py-3 text-gray-900 text-right">${(cost.current_monthly || 0).toFixed(2)}</td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Inefficiencies */}
                    {inefficiencies.length > 0 && (
                        <div className="px-6 py-4">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> Inefficiencies Detected
                            </h5>
                            <div className="space-y-2">
                                {inefficiencies.map((ineff, i) => {
                                    const isev = SEVERITY_BADGE[ineff.severity] || SEVERITY_BADGE.medium
                                    return (
                                        <div key={i} className="flex items-start gap-3 bg-amber-50/60 rounded-xl p-4 border border-amber-100">
                                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-lg border flex-shrink-0 mt-0.5 ${isev}`}>
                                                #{ineff.id || i + 1}
                                            </span>
                                            <div>
                                                <p className="text-sm text-gray-800 font-medium">{cleanDisplayText(ineff.description)}</p>
                                                {ineff.evidence && <p className="text-xs text-gray-500 mt-1">{cleanDisplayText(ineff.evidence)}</p>}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* Recommendation content: full analysis or structured blocks */}
                    {recommendations.map((rec, i) => (
                        <div key={i} className="px-6 py-5 border-t border-gray-100">
                            <div className="flex items-center gap-3 mb-5">
                                <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold">
                                    {i + 1}
                                </div>
                                <h4 className="text-base font-bold text-gray-900">
                                    {cleanDisplayText(rec.title || rec.full_analysis?.split('\n')[0] || `Recommendation ${i + 1}`)}
                                </h4>
                            </div>

                            {/* Full LLM analysis (clean, no symbols) */}
                            {(rec.full_analysis || card.raw_analysis) && (
                                <div className="mb-6 bg-gradient-to-br from-blue-50 to-white border border-blue-100 rounded-xl p-5 shadow-sm">
                                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap font-[inherit]">
                                        {cleanDisplayText(rec.full_analysis || card.raw_analysis || '')}
                                    </p>
                                </div>
                            )}

                            {/* Action + Savings pill */}
                            <div className="flex flex-wrap items-center gap-3 mb-6 pb-4 border-b border-gray-100">
                                {Number(rec.estimated_monthly_savings) > 0 && (
                                    <span className="text-xs bg-emerald-100 text-emerald-700 px-4 py-2 rounded-full font-bold border border-emerald-300 shadow-sm">
                                        💰 Saves ${Number(rec.estimated_monthly_savings).toFixed(2)}/mo
                                    </span>
                                )}
                                {rec.confidence && (
                                    <span className="text-xs bg-blue-100 text-blue-700 px-4 py-2 rounded-full font-medium border border-blue-300 shadow-sm">
                                        ✓ {rec.confidence} confidence
                                    </span>
                                )}
                            </div>

                            {/* Implementation Steps */}
                            {rec.implementation_steps?.length > 0 && (
                                <div className="mb-6">
                                    <p className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-4">Implementation Steps</p>
                                    <div className="space-y-3">
                                        {rec.implementation_steps.map((step, si) => (
                                            <div key={si} className="flex items-start gap-4 bg-gray-50 rounded-lg p-4 border border-gray-200">
                                                <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 text-sm font-bold">
                                                    {si + 1}
                                                </div>
                                                <p className="text-sm text-gray-700 leading-relaxed pt-0.5">{cleanDisplayText(String(step).replace(/^\d+\.\s*/, ''))}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Performance + Risk */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {rec.performance_impact && (
                                    <div className="bg-blue-50/80 rounded-xl p-4 border border-blue-100">
                                        <p className="text-[10px] font-bold text-blue-600 uppercase mb-1.5 flex items-center gap-1">
                                            <Activity className="w-3 h-3" /> Performance Impact
                                        </p>
                                        <p className="text-xs text-gray-700 leading-relaxed">{cleanDisplayText(rec.performance_impact)}</p>
                                    </div>
                                )}
                                {rec.risk_mitigation && (
                                    <div className="bg-amber-50/80 rounded-xl p-4 border border-amber-100">
                                        <p className="text-[10px] font-bold text-amber-600 uppercase mb-1.5 flex items-center gap-1">
                                            <Shield className="w-3 h-3" /> Risk Mitigation
                                        </p>
                                        <p className="text-xs text-gray-700 leading-relaxed">{cleanDisplayText(rec.risk_mitigation)}</p>
                                    </div>
                                )}
                            </div>

                            {rec.validation_steps?.length > 0 && (
                                <div className="mt-4 flex flex-wrap gap-2">
                                    {rec.validation_steps.map((v, vi) => (
                                        <span key={vi} className="text-xs bg-gray-100 text-gray-600 px-3 py-1.5 rounded-full border border-gray-200 inline-flex items-center gap-1.5">
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> {cleanDisplayText(String(v))}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}

                    {/* Standalone raw analysis if no recommendations block */}
                    {!recommendations.length && card.raw_analysis && (
                        <div className="px-6 py-5">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <Sparkles className="w-4 h-4 text-indigo-500" /> Full analysis
                            </h5>
                            <div className="rounded-2xl bg-white border border-gray-100 p-5 shadow-sm">
                                <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                                    {cleanDisplayText(card.raw_analysis)}
                                </p>
                            </div>
                        </div>
                    )}

                    {/* FinOps Best Practice */}
                    {card.finops_best_practice && (
                        <div className="px-6 py-4">
                            <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <BookOpen className="w-3.5 h-3.5 text-emerald-500" /> AWS FinOps Best Practice
                            </h5>
                            <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100">
                                <p className="text-sm text-emerald-800 leading-relaxed">{cleanDisplayText(card.finops_best_practice)}</p>
                            </div>
                        </div>
                    )}

                    {/* Footer */}
                    <div className="px-6 py-4 bg-gray-50/80 border-t border-gray-100">
                        <div className="flex items-center gap-2">
                            <BrainCircuit className="w-4 h-4 text-gray-400" />
                            <span className="text-xs text-gray-500">
                                FinOps AI · Priority #{card.priority} · Risk: {card.risk_level || 'medium'}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

/* ── Finding Card ────────────────────────────────────────── */
function FindingCard({ finding }) {
    const sev = SEV[finding.severity] || SEV.moderate
    const agent = AGENT_META[finding.source_agent] || { color: '#6b7280', icon: FileText, label: '?' }
    const SevIcon = sev.icon; const AgentIcon = agent.icon
    return (
        <div className="rounded-xl p-4 border transition-all duration-200 hover:shadow-sm" style={{ backgroundColor: sev.bg, borderColor: sev.border }}>
            <div className="flex items-start gap-3">
                <SevIcon className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: sev.text }} />
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                        <span className={`badge ${sev.badge} text-[10px]`}>{finding.severity.toUpperCase()}</span>
                        <span className="text-[10px] flex items-center gap-1" style={{ color: agent.color }}><AgentIcon className="w-3 h-3" /> {agent.label}</span>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: sev.text }}>{finding.description}</p>
                    {finding.affected_node && <p className="text-xs text-gray-400 mt-1.5">Resource: <code className="text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded font-medium">{finding.affected_node}</code></p>}
                </div>
            </div>
        </div>
    )
}

/* ── Agent Pipeline ──────────────────────────────────────── */
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
            <h3 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2"><BrainCircuit className="w-4 h-4 text-blue-600" />5-Agent Pipeline</h3>
            <div className="space-y-1.5">{steps.map(({ key, label }, i) => {
                const meta = AGENT_META[key]; const Icon = meta.icon; const done = !!agentResults?.[key]; const ms = timings?.[key] || 0
                return (<div key={key} className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold" style={{ backgroundColor: meta.color + '12', color: meta.color }}>{i + 1}</div>
                    <Icon className="w-4 h-4" style={{ color: meta.color }} /><span className="text-sm text-gray-600 flex-1">{label}</span>
                    {done ? <div className="flex items-center gap-2"><span className="text-[10px] text-gray-400">{ms}ms</span><CheckCircle2 className="w-4 h-4 text-emerald-500" /></div> : <div className="w-4 h-4 border-2 border-gray-200 rounded-full" />}
                </div>)
            })}</div>
            {timings?.total_ms && <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between"><span className="text-xs text-gray-400">Total pipeline</span><span className="text-xs font-bold text-blue-600 flex items-center gap-1"><Clock className="w-3 h-3" /> {timings.total_ms}ms</span></div>}
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Deep Analysis Components
 ═══════════════════════════════════════════════════════════════ */

/* ── Node Metrics Table ──────────────────────────────────── */
function NodeMetricsTable({ metrics, onSelectNode }) {
    const [sortField, setSortField] = useState('betweenness_centrality')
    const [sortDir, setSortDir] = useState('desc')
    const [showAll, setShowAll] = useState(false)

    const sorted = [...metrics].sort((a, b) => {
        const va = a[sortField] ?? 0, vb = b[sortField] ?? 0
        return sortDir === 'desc' ? vb - va : va - vb
    })
    const display = showAll ? sorted : sorted.slice(0, 15)

    const cols = [
        { key: 'name', label: 'Node', sort: false },
        { key: 'node_type', label: 'Type', sort: false },
        { key: 'betweenness_centrality', label: 'Centrality' },
        { key: 'pagerank', label: 'PageRank' },
        { key: 'clustering_coefficient', label: 'Clustering' },
        { key: 'in_degree', label: 'In°' },
        { key: 'out_degree', label: 'Out°' },
        { key: 'cost_monthly', label: 'Cost/mo' },
        { key: 'cost_per_dependency', label: 'Cost/Dep' },
        { key: 'health_score', label: 'Health' },
    ]

    function toggleSort(field) {
        if (sortField === field) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
        else { setSortField(field); setSortDir('desc') }
    }

    function cellColor(field, val) {
        if (field === 'betweenness_centrality') return val > 0.3 ? 'text-red-700 font-bold' : val > 0.1 ? 'text-amber-700 font-semibold' : ''
        if (field === 'health_score') return val < 50 ? 'text-red-700 font-bold' : val < 70 ? 'text-amber-700 font-semibold' : 'text-emerald-700'
        if (field === 'cost_monthly') return val > 500 ? 'text-red-700 font-bold' : val > 100 ? 'text-amber-700' : ''
        if (field === 'in_degree') return val >= 5 ? 'text-violet-700 font-bold' : ''
        return ''
    }

    return (
        <div className="card overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-indigo-600" />
                    Per-Node Metrics ({metrics.length} nodes)
                </h3>
                {metrics.length > 15 && (
                    <button onClick={() => setShowAll(!showAll)} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
                        {showAll ? 'Show Top 15' : `Show All ${metrics.length}`}
                    </button>
                )}
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                            {cols.map(c => (
                                <th key={c.key}
                                    onClick={() => c.sort !== false && toggleSort(c.key)}
                                    className={`px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap ${c.sort !== false ? 'cursor-pointer hover:text-gray-700' : ''}`}>
                                    <span className="flex items-center gap-1">
                                        {c.label}
                                        {sortField === c.key && (sortDir === 'desc' ? <ArrowDown className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />)}
                                    </span>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {display.map((m, i) => (
                            <tr key={m.node_id} className="hover:bg-blue-50/30 cursor-pointer transition-colors"
                                onClick={() => onSelectNode?.(m.node_id)}>
                                <td className="px-3 py-2 font-medium text-gray-900 max-w-[180px] truncate" title={m.name}>{m.name}</td>
                                <td className="px-3 py-2"><span className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 text-[10px]">{m.node_type}</span></td>
                                <td className={`px-3 py-2 font-mono ${cellColor('betweenness_centrality', m.betweenness_centrality)}`}>{m.betweenness_centrality.toFixed(4)}</td>
                                <td className="px-3 py-2 font-mono">{m.pagerank.toFixed(4)}</td>
                                <td className="px-3 py-2 font-mono">{m.clustering_coefficient.toFixed(4)}</td>
                                <td className={`px-3 py-2 font-mono ${cellColor('in_degree', m.in_degree)}`}>{m.in_degree}</td>
                                <td className="px-3 py-2 font-mono">{m.out_degree}</td>
                                <td className={`px-3 py-2 font-mono ${cellColor('cost_monthly', m.cost_monthly)}`}>${m.cost_monthly.toFixed(2)}</td>
                                <td className="px-3 py-2 font-mono">${m.cost_per_dependency.toFixed(2)}</td>
                                <td className={`px-3 py-2 font-mono ${cellColor('health_score', m.health_score)}`}>{m.health_score.toFixed(0)}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

/* ── Interesting Node Card (expandable) ──────────────────── */
function InterestingNodeCard({ node, isExpanded, onToggle }) {
    const m = node.metrics
    const cascade = CASCADE_COLORS[node.cascading_failure_risk] || CASCADE_COLORS.low

    return (
        <div className="card overflow-hidden transition-all duration-300 hover:shadow-md">
            {/* Header bar with risk color */}
            <div className={`h-1.5 ${RISK_COLORS[m.risk_level] || RISK_COLORS.low}`} />

            <div className="p-5">
                {/* Top row */}
                <button onClick={onToggle} className="w-full text-left">
                    <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${m.risk_level === 'critical' ? 'bg-red-100 text-red-600' :
                                m.risk_level === 'high' ? 'bg-orange-100 text-orange-600' :
                                    m.risk_level === 'medium' ? 'bg-amber-100 text-amber-600' :
                                        'bg-blue-100 text-blue-600'
                                }`}>
                                {node.single_point_of_failure ? <AlertTriangle className="w-5 h-5" /> :
                                    m.betweenness_centrality > 0.3 ? <Flame className="w-5 h-5" /> :
                                        <CircleDot className="w-5 h-5" />}
                            </div>
                            <div className="min-w-0 flex-1">
                                <h4 className="text-sm font-bold text-gray-900 truncate">{node.name}</h4>
                                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                    <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 rounded text-gray-600">{node.node_type}</span>
                                    {node.single_point_of_failure && (
                                        <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded font-bold">SPOF</span>
                                    )}
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${cascade}`}>
                                        {node.cascading_failure_risk.toUpperCase()} cascade risk
                                    </span>
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-4 flex-shrink-0">
                            <div className="text-right">
                                <p className="text-lg font-bold text-gray-900">${m.cost_monthly.toFixed(2)}</p>
                                <p className="text-[10px] text-gray-400">{m.cost_share.toFixed(1)}% of total</p>
                            </div>
                            <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                        </div>
                    </div>
                </button>

                {/* Quick metrics strip */}
                <div className="grid grid-cols-6 gap-2 mt-4">
                    <MetricPill label="Centrality" value={m.betweenness_centrality.toFixed(4)} color={m.betweenness_centrality > 0.3 ? 'red' : m.betweenness_centrality > 0.1 ? 'amber' : 'blue'} small />
                    <MetricPill label="PageRank" value={m.pagerank.toFixed(4)} color="indigo" small />
                    <MetricPill label="Clustering" value={m.clustering_coefficient.toFixed(4)} color="violet" small />
                    <MetricPill label="In-degree" value={m.in_degree} color={m.in_degree >= 5 ? 'red' : 'blue'} small />
                    <MetricPill label="Out-degree" value={m.out_degree} color="blue" small />
                    <MetricPill label="Health" value={`${m.health_score.toFixed(0)}%`} color={m.health_score < 50 ? 'red' : m.health_score < 70 ? 'amber' : 'emerald'} small />
                </div>

                {/* Reasons flagged */}
                <div className="mt-3">
                    <p className="text-[10px] font-bold text-gray-400 uppercase mb-1.5">Flagged because</p>
                    <div className="space-y-1">
                        {node.interesting_reasons.map((r, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs text-gray-600">
                                <AlertCircle className="w-3 h-3 text-amber-500 flex-shrink-0 mt-0.5" />
                                <span>{r}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                    <div className="mt-5 pt-5 border-t border-gray-100 space-y-5 animate-fade-in-up">
                        {/* Dependencies & Dependents side by side */}
                        <div className="grid grid-cols-2 gap-4">
                            {/* Dependents */}
                            <div>
                                <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                    <ArrowDown className="w-3 h-3 text-red-500" />
                                    Dependents ({node.dependents?.length || 0} services depend on this)
                                </h5>
                                {node.dependents?.length > 0 ? (
                                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                        {node.dependents.map((d, i) => (
                                            <div key={i} className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg text-xs">
                                                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${d.health_score < 70 ? 'bg-red-500' : 'bg-emerald-500'}`} />
                                                <span className="font-medium text-gray-900 flex-1 truncate" title={d.name}>{d.name}</span>
                                                <span className="text-gray-400 text-[10px]">{d.edge_type}</span>
                                                <span className="text-gray-500 font-mono">{d.weight.toFixed(1)}</span>
                                            </div>
                                        ))}
                                    </div>
                                ) : <p className="text-xs text-gray-400 italic">No services depend on this node</p>}
                            </div>

                            {/* Dependencies */}
                            <div>
                                <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                    <ArrowRight className="w-3 h-3 text-blue-500" />
                                    Dependencies ({node.dependencies?.length || 0} downstream services)
                                </h5>
                                {node.dependencies?.length > 0 ? (
                                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                        {node.dependencies.map((d, i) => (
                                            <div key={i} className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg text-xs">
                                                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${d.health_score < 70 ? 'bg-red-500' : 'bg-emerald-500'}`} />
                                                <span className="font-medium text-gray-900 flex-1 truncate" title={d.name}>{d.name}</span>
                                                <span className="text-gray-400 text-[10px]">{d.edge_type}</span>
                                                <span className="text-gray-500 font-mono">${d.cost_monthly.toFixed(2)}</span>
                                            </div>
                                        ))}
                                    </div>
                                ) : <p className="text-xs text-gray-400 italic">No downstream dependencies</p>}
                            </div>
                        </div>

                        {/* Dependency Patterns */}
                        {node.dependency_patterns?.length > 0 && (
                            <div>
                                <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                    <Workflow className="w-3 h-3 text-violet-500" /> Architectural Patterns
                                </h5>
                                <div className="space-y-1.5">
                                    {node.dependency_patterns.map((p, i) => (
                                        <div key={i} className="flex items-start gap-2 p-2.5 bg-violet-50 border border-violet-100 rounded-lg text-xs text-violet-800">
                                            <Zap className="w-3 h-3 flex-shrink-0 mt-0.5 text-violet-500" />
                                            <span>{p}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Peer Comparison */}
                        {node.peer_comparison?.peer_count > 0 && (
                            <div>
                                <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                    <BarChart2 className="w-3 h-3 text-blue-500" /> Peer Comparison ({node.peer_comparison.peer_count} {node.peer_comparison.peer_type} peers)
                                </h5>
                                <div className="grid grid-cols-4 gap-2">
                                    <div className="p-2.5 bg-blue-50 border border-blue-100 rounded-lg">
                                        <p className="text-[10px] text-gray-400">This Cost</p>
                                        <p className="text-sm font-bold text-gray-900">${node.peer_comparison.this_cost.toFixed(2)}</p>
                                    </div>
                                    <div className="p-2.5 bg-blue-50 border border-blue-100 rounded-lg">
                                        <p className="text-[10px] text-gray-400">Peer Avg</p>
                                        <p className="text-sm font-bold text-gray-900">${node.peer_comparison.avg_cost.toFixed(2)}</p>
                                    </div>
                                    <div className="p-2.5 bg-blue-50 border border-blue-100 rounded-lg">
                                        <p className="text-[10px] text-gray-400">Cost Ratio</p>
                                        <p className={`text-sm font-bold ${node.peer_comparison.cost_ratio > 2 ? 'text-red-700' : node.peer_comparison.cost_ratio > 1.5 ? 'text-amber-700' : 'text-emerald-700'}`}>
                                            {node.peer_comparison.cost_ratio.toFixed(1)}x
                                        </p>
                                    </div>
                                    <div className="p-2.5 bg-blue-50 border border-blue-100 rounded-lg">
                                        <p className="text-[10px] text-gray-400">Health vs Peers</p>
                                        <p className={`text-sm font-bold ${node.peer_comparison.this_health < node.peer_comparison.avg_health - 10 ? 'text-red-700' : 'text-emerald-700'}`}>
                                            {node.peer_comparison.this_health.toFixed(0)}% vs {node.peer_comparison.avg_health.toFixed(0)}%
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Behavioral Flags */}
                        {node.behavioral_flags?.length > 0 && (
                            <div>
                                <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                    <Activity className="w-3 h-3 text-orange-500" /> Behavioral Analysis
                                </h5>
                                <div className="space-y-1.5">
                                    {node.behavioral_flags.map((flag, i) => {
                                        const isCrit = flag.startsWith('CRITICAL')
                                        const isWarn = flag.startsWith('WARNING')
                                        const isErr = flag.startsWith('ERROR') || flag.startsWith('WASTE')
                                        return (
                                            <div key={i} className={`flex items-start gap-2 p-2.5 rounded-lg text-xs border ${isCrit ? 'bg-red-50 border-red-100 text-red-800' :
                                                isWarn ? 'bg-amber-50 border-amber-100 text-amber-800' :
                                                    isErr ? 'bg-orange-50 border-orange-100 text-orange-800' :
                                                        'bg-blue-50 border-blue-100 text-blue-800'
                                                }`}>
                                                {isCrit ? <XCircle className="w-3 h-3 flex-shrink-0 mt-0.5" /> :
                                                    isWarn ? <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" /> :
                                                        <Activity className="w-3 h-3 flex-shrink-0 mt-0.5" />}
                                                <span>{flag}</span>
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Full Narrative */}
                        <div>
                            <h5 className="text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                <FileText className="w-3 h-3 text-cyan-500" /> Full Analysis Narrative
                            </h5>
                            <div className="bg-gray-900 text-green-400 rounded-lg p-4 max-h-80 overflow-auto text-xs font-mono leading-relaxed border border-gray-700 whitespace-pre-wrap">
                                {node.narrative}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

/* ── Deep Analysis Summary Dashboard ─────────────────────── */
function DeepAnalysisSummary({ report }) {
    const s = report.summary
    return (
        <div className="space-y-5">
            {/* Top stats */}
            <div className="grid grid-cols-6 gap-3">
                <div className="card p-4 border-indigo-200">
                    <p className="text-[10px] text-gray-400 uppercase">Nodes</p>
                    <p className="text-xl font-bold text-gray-900">{report.total_nodes}</p>
                </div>
                <div className="card p-4 border-indigo-200">
                    <p className="text-[10px] text-gray-400 uppercase">Edges</p>
                    <p className="text-xl font-bold text-gray-900">{report.total_edges}</p>
                </div>
                <div className="card p-4 border-indigo-200">
                    <p className="text-[10px] text-gray-400 uppercase">Total Cost</p>
                    <p className="text-xl font-bold text-gray-900">${report.total_cost.toLocaleString()}</p>
                </div>
                <div className="card p-4 border-indigo-200">
                    <p className="text-[10px] text-gray-400 uppercase">Interesting</p>
                    <p className="text-xl font-bold text-amber-600">{s.total_interesting}</p>
                </div>
                <div className="card p-4 border-red-200">
                    <p className="text-[10px] text-gray-400 uppercase">SPOF</p>
                    <p className="text-xl font-bold text-red-600">{s.spof_count}</p>
                </div>
                <div className="card p-4 border-indigo-200">
                    <p className="text-[10px] text-gray-400 uppercase">DAG</p>
                    <p className="text-xl font-bold text-gray-900">{report.is_dag ? 'Yes' : 'No'}</p>
                </div>
            </div>

            {/* Risk & Type Distribution */}
            <div className="grid grid-cols-2 gap-4">
                {/* Risk distribution */}
                <div className="card p-5">
                    <h4 className="text-xs font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                        <Shield className="w-3.5 h-3.5 text-red-500" /> Risk Distribution
                    </h4>
                    <div className="space-y-2">
                        {Object.entries(s.risk_distribution || {}).map(([level, count]) => {
                            const total = report.total_nodes || 1
                            const pct = (count / total) * 100
                            return (
                                <div key={level} className="flex items-center gap-3">
                                    <span className={`text-xs font-medium w-16 capitalize ${level === 'critical' ? 'text-red-700' :
                                        level === 'high' ? 'text-orange-700' :
                                            level === 'medium' ? 'text-amber-700' : 'text-emerald-700'
                                        }`}>{level}</span>
                                    <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                                        <div className={`h-full rounded-full ${RISK_COLORS[level] || 'bg-gray-400'}`} style={{ width: `${pct}%` }} />
                                    </div>
                                    <span className="text-xs text-gray-500 font-mono w-12 text-right">{count} ({pct.toFixed(0)}%)</span>
                                </div>
                            )
                        })}
                    </div>
                </div>

                {/* Type distribution */}
                <div className="card p-5">
                    <h4 className="text-xs font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-indigo-500" /> Service Type Distribution
                    </h4>
                    <div className="space-y-2">
                        {Object.entries(s.type_distribution || {}).slice(0, 8).map(([type, count]) => {
                            const total = report.total_nodes || 1
                            const pct = (count / total) * 100
                            return (
                                <div key={type} className="flex items-center gap-3">
                                    <span className="text-xs font-medium w-24 truncate text-gray-700">{type}</span>
                                    <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                                        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                                    </div>
                                    <span className="text-xs text-gray-500 font-mono w-12 text-right">{count}</span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            </div>

            {/* Top bottlenecks + cost hotspots */}
            <div className="grid grid-cols-2 gap-4">
                <div className="card p-5">
                    <h4 className="text-xs font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                        <Flame className="w-3.5 h-3.5 text-orange-500" /> Top Bottlenecks (Centrality)
                    </h4>
                    <div className="space-y-2">
                        {(s.top_bottlenecks || []).map((b, i) => (
                            <div key={i} className="flex items-center gap-2">
                                <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${i === 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>{i + 1}</span>
                                <span className="text-xs font-medium text-gray-900 flex-1 truncate">{b.name}</span>
                                <span className="text-xs font-mono text-gray-500">{b.centrality.toFixed(4)}</span>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="card p-5">
                    <h4 className="text-xs font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                        <DollarSign className="w-3.5 h-3.5 text-emerald-500" /> Top Cost Hotspots
                    </h4>
                    <div className="space-y-2">
                        {(s.top_cost_hotspots || []).map((h, i) => (
                            <div key={i} className="flex items-center gap-2">
                                <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${i === 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>{i + 1}</span>
                                <span className="text-xs font-medium text-gray-900 flex-1 truncate">{h.name}</span>
                                <span className="text-xs font-mono text-gray-500">${h.cost_monthly.toFixed(2)} ({h.cost_share.toFixed(1)}%)</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Cascade risks */}
            {(s.cascade_risks || []).length > 0 && (
                <div className="card p-5 border-red-200 bg-red-50/20">
                    <h4 className="text-xs font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-red-500" /> High Cascade Risk Nodes
                    </h4>
                    <div className="space-y-2">
                        {s.cascade_risks.map((r, i) => (
                            <div key={i} className="flex items-center gap-3 p-2 bg-white rounded-lg border border-red-100">
                                {r.spof && <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded font-bold">SPOF</span>}
                                <span className="text-xs font-medium text-gray-900 flex-1">{r.name}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${CASCADE_COLORS[r.risk]}`}>{r.risk.toUpperCase()}</span>
                                <span className="text-xs text-gray-500">{r.dependents} dependents</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════
   Main Page
 ═══════════════════════════════════════════════════════════════ */
export default function AnalysisPage() {
    const location = useLocation()
    const [architectures, setArchitectures] = useState([])
    const [selectedArch, setSelectedArch] = useState(location.state?.arch || null)
    const [result, setResult] = useState(null)
    const [loading, setLoading] = useState(false)
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const [findingFilter, setFindingFilter] = useState('all')
    const [awsProgress, setAwsProgress] = useState(null)
    const awsPollRef = useRef(null)
    const awsStartRef = useRef(null)
    const awsTimerRef = useRef(null)

    // Deep analysis state
    const [activeTab, setActiveTab] = useState('recommendations')  // recommendations only
    const [deepReport, setDeepReport] = useState(null)
    const [deepLoading, setDeepLoading] = useState(false)
    const [deepError, setDeepError] = useState(null)
    const [expandedNodes, setExpandedNodes] = useState({})
    const [scrollToNode, setScrollToNode] = useState(null)
    const nodeRefs = useRef({})

    // Recommendation engine state
    const [recResult, setRecResult] = useState(null)
    const [recLoading, setRecLoading] = useState(false)
    const [recError, setRecError] = useState(null)
    const [expandedCards, setExpandedCards] = useState({})
    const [recRefreshing, setRecRefreshing] = useState(false)  // Background refresh state

    // Recommendation history state
    const [recHistory, setRecHistory] = useState([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState(null)
    const [selectedHistorySnapshot, setSelectedHistorySnapshot] = useState(null)

    // LLM report state (from 5-agent pipeline)
    const [llmReport, setLlmReport] = useState(null)
    const [llmReportHistory, setLlmReportHistory] = useState([])
    const [llmHistoryLoading, setLlmHistoryLoading] = useState(false)
    const [llmHistoryError, setLlmHistoryError] = useState(null)

    useEffect(() => {
        listArchitectures()
            .then(res => setArchitectures(res.data.architectures))
            .catch(() => { })
        return () => cancelAwsDiscovery()
    }, [])

    // Load latest stored recommendations immediately when architecture is selected.
    // Do NOT trigger background refresh on page open; cron pipeline owns refresh cadence.
    useEffect(() => {
        if (selectedArch) {
            loadLastRecommendations()
        }
    }, [selectedArch])

    // Scroll to node when selected from metrics table
    useEffect(() => {
        if (scrollToNode && nodeRefs.current[scrollToNode]) {
            nodeRefs.current[scrollToNode].scrollIntoView({ behavior: 'smooth', block: 'center' })
            setExpandedNodes(prev => ({ ...prev, [scrollToNode]: true }))
            setScrollToNode(null)
        }
    }, [scrollToNode, deepReport])

    function cancelAwsDiscovery() {
        if (awsPollRef.current) clearInterval(awsPollRef.current)
        if (awsTimerRef.current) clearInterval(awsTimerRef.current)
        awsPollRef.current = null; awsTimerRef.current = null
    }

    async function handleAwsLiveAnalysis() {
        setDropdownOpen(false); setResult(null); setDeepReport(null); setLoading(false)
        setAwsProgress({ stage: 'queued', detail: 'Starting AWS discovery...', elapsed: 0 })
        awsStartRef.current = Date.now()
        awsTimerRef.current = setInterval(() => {
            setAwsProgress(prev => prev ? { ...prev, elapsed: (Date.now() - awsStartRef.current) / 1000 } : prev)
        }, 500)
        try {
            const res = await ingestFromAws('us-east-1')
            const snapshotId = res.data?.snapshot_id
            if (!snapshotId) { setAwsProgress(prev => ({ ...prev, stage: 'failed', detail: 'No snapshot_id returned' })); cancelAwsDiscovery(); return }
            awsPollRef.current = setInterval(async () => {
                try {
                    const elapsedMs = Date.now() - awsStartRef.current
                    if (elapsedMs > 5 * 60 * 1000) { cancelAwsDiscovery(); setAwsProgress(prev => ({ ...prev, stage: 'failed', detail: 'Timed out after 5 min', error: 'Timed out' })); return }
                    const st = await getAwsPipelineStatus(snapshotId)
                    const d = st.data
                    setAwsProgress(prev => ({ ...prev, stage: d.pipeline_stage || d.status, detail: d.pipeline_detail || '', totalServices: d.total_services || 0, totalCost: d.total_cost_monthly || 0, error: d.error_message || null }))
                    if (d.status === 'completed') {
                        cancelAwsDiscovery()
                        try { const refreshed = await listArchitectures(); setArchitectures(refreshed.data.architectures) } catch { }
                        const archId = d.architecture_id
                        if (archId) {
                            const arch = { architecture_id: archId, name: `AWS Live (${archId.slice(0, 8)})`, filename: null }
                            setSelectedArch(arch)
                        }
                    } else if (d.status === 'failed') { cancelAwsDiscovery() }
                } catch { }
            }, 1500)
        } catch (e) {
            setAwsProgress(prev => ({ ...prev, stage: 'failed', detail: e.message || 'Failed' })); cancelAwsDiscovery()
        }
    }

    async function runDeepAnalysis() {
        if (!selectedArch) return
        setDeepLoading(true); setDeepReport(null); setDeepError(null); setExpandedNodes({})
        try {
            const res = await deepGraphAnalysis(selectedArch.architecture_id, selectedArch.filename)
            setDeepReport(res.data)
        } catch (e) {
            console.error('Deep analysis failed:', e)
            setDeepError(e.response?.data?.detail || e.message || 'Analysis failed')
        }
        setDeepLoading(false)
    }

    async function runAgentAnalysis() {
        if (!selectedArch) return
        setLoading(true); setResult(null)
        try {
            const res = await analyzeArchitecture(selectedArch.filename, selectedArch.architecture_id)
            setResult(res.data)
            setLlmReport(res.data)
            loadLLMReportHistory()
        } catch (e) { console.error('Analysis failed:', e) }
        setLoading(false)
    }

    async function runRecommendations() {
        if (!selectedArch) return
        setRecLoading(true); setRecResult(null); setRecError(null); setExpandedCards({})
        try {
            const res = await generateRecommendations(selectedArch.architecture_id, selectedArch.filename)
            setRecResult(res.data)
        } catch (e) {
            console.error('Recommendation generation failed:', e)
            setRecError(e.response?.data?.detail || e.message || 'Recommendation generation failed')
        }
        setRecLoading(false)
    }

    async function loadLastRecommendations() {
        if (!selectedArch) return
        setRecError(null)
        try {
            const res = await getLastRecommendations(selectedArch.architecture_id, selectedArch.filename)
            setRecResult(res.data)
        } catch (e) {
            setRecError(e.response?.data?.detail || e.message || 'No stored result found')
        }
    }

    async function loadRecommendationHistory() {
        if (!selectedArch) return
        setHistoryError(null)
        setHistoryLoading(true)
        try {
            const res = await getRecommendationsHistory(selectedArch.architecture_id, selectedArch.filename, 15)
            setRecHistory(res.data.history || [])
        } catch (e) {
            setHistoryError(e.response?.data?.detail || e.message || 'Failed to load history')
        } finally {
            setHistoryLoading(false)
        }
    }

    async function loadLLMReportHistory() {
        if (!selectedArch) return
        setLlmHistoryError(null)
        setLlmHistoryLoading(true)
        try {
            const res = await getLLMReportHistory(selectedArch.architecture_id, selectedArch.filename, 15)
            setLlmReportHistory(res.data.history || [])
        } catch (e) {
            setLlmHistoryError(e.response?.data?.detail || e.message || 'Failed to load history')
        } finally {
            setLlmHistoryLoading(false)
        }
    }

    async function loadLatestLLMReport() {
        if (!selectedArch) return
        try {
            const res = await getLatestLLMReport(selectedArch.architecture_id, selectedArch.filename)
            if (res.data.status !== 'none') {
                setLlmReport(res.data)
            }
        } catch (e) {
            console.error('Failed to load latest LLM report:', e)
        }
    }

    // Load history when tab is switched
    useEffect(() => {
        if (activeTab === 'history' && selectedArch) {
            loadRecommendationHistory()
        }
    }, [activeTab, selectedArch])

    // Load LLM report and history when agents tab is opened
    useEffect(() => {
        if (activeTab === 'agents' && selectedArch) {
            loadLatestLLMReport()
            loadLLMReportHistory()
        }
    }, [activeTab, selectedArch])

    function handleSelectNode(nodeId) {
        // Check if the node exists in interesting nodes
        const found = deepReport?.interesting_nodes?.find(n => n.node_id === nodeId)
        if (found) {
            setScrollToNode(nodeId)
        }
    }

    const filteredFindings = result?.all_findings?.filter(f =>
        findingFilter === 'all' || f.severity === findingFilter
    ) || []

    const tabs = [
        { key: 'recommendations', label: 'Recommendation Cards', icon: Lightbulb },
        { key: 'history', label: 'History', icon: History },
        { key: 'deep', label: 'Deep Metrics', icon: Network },
        { key: 'agents', label: '5-Agent Pipeline', icon: BrainCircuit },
    ]

    const recommendationItems = recResult?.recommendations || []

    const isSummaryRecommendation = (rec) => {
        if (!rec) return false
        const title = String(rec.title || '').trim().toLowerCase()
        const description = String(rec.description || '').trim().toLowerCase()
        return title.startsWith('summary of recommendations') ||
            description.startsWith('summary of recommendations')
    }

    const parseMoneyValue = (value) => {
        if (typeof value === 'number') return Number.isFinite(value) ? value : 0
        if (typeof value !== 'string') return 0

        let normalized = value.replace(/[$\s]/g, '')
        if (!normalized) return 0

        if (normalized.includes(',') && normalized.includes('.')) {
            normalized = normalized.replace(/,/g, '')
        } else if (normalized.includes(',') && !normalized.includes('.')) {
            normalized = /,\d{1,2}$/.test(normalized)
                ? normalized.replace(',', '.')
                : normalized.replace(/,/g, '')
        }

        const parsed = Number(normalized)
        return Number.isFinite(parsed) ? parsed : 0
    }

    const summaryRecommendation = recommendationItems.find(isSummaryRecommendation) || null
    const displayRecommendations = recommendationItems.filter(rec => !isSummaryRecommendation(rec))

    const computedTotalSavings = displayRecommendations.reduce((sum, rec) => {
        const cardSavings = rec?.total_estimated_savings ?? rec?.estimated_monthly_savings ?? 0
        return sum + parseMoneyValue(cardSavings)
    }, 0)

    const displayedTotalSavings = computedTotalSavings > 0
        ? computedTotalSavings
        : parseMoneyValue(recResult?.total_estimated_savings)

    const summaryTextRaw = summaryRecommendation?.description ||
        summaryRecommendation?.recommendations?.[0]?.recommendation ||
        summaryRecommendation?.recommendations?.[0]?.reasoning ||
        ''

    const summaryLines = summaryTextRaw
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !/^summary of recommendations:?$/i.test(line))

    const fallbackSummaryLines = displayRecommendations.slice(0, 10).map((rec, idx) => {
        const label = rec?.title || rec?.recommendations?.[0]?.action || 'Optimization action'
        const recSavings = parseMoneyValue(rec?.total_estimated_savings ?? rec?.estimated_monthly_savings ?? 0)
        return recSavings > 0
            ? `${idx + 1}. ${label} — Estimated savings: $${recSavings.toFixed(2)}/mo`
            : `${idx + 1}. ${label}`
    })

    const summaryDisplayLines = summaryLines.length > 0 ? summaryLines : fallbackSummaryLines

    return (
        <div className="max-w-7xl mx-auto px-6 py-10">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                        <BrainCircuit className="w-7 h-7 text-blue-600" />
                        AI Analysis
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Deep graph metrics • Per-node narratives • 5-agent AI pipeline
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
                            <button onClick={handleAwsLiveAnalysis}
                                className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium text-amber-700 hover:bg-amber-50 transition-colors border-b border-gray-100 mb-1 flex items-center gap-2">
                                <Cloud className="w-4 h-4 text-amber-600" /> AWS Live Discovery
                                <span className="ml-auto text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                                    <Shield className="w-3 h-3" /> Live + Security
                                </span>
                            </button>
                            {architectures.map(a => (
                                <button key={a.filename || a.architecture_id}
                                    onClick={() => { setSelectedArch(a); setDropdownOpen(false); setResult(null); setDeepReport(null); setRecResult(null) }}
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

            {/* AWS Progress */}
            {awsProgress && <AwsProgressBar progress={awsProgress} onCancel={() => { cancelAwsDiscovery(); setAwsProgress(null) }} />}

            {/* Tab bar */}
            {selectedArch && (
                <div className="flex gap-1 p-1 bg-gray-100 rounded-xl border border-gray-200 w-fit mb-6">
                    {tabs.map(({ key, label, icon: Icon }) => (
                        <button key={key} onClick={() => setTab(key)}
                            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === key ? 'bg-white text-blue-700 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-700'}`}
                        >
                            <Icon className="w-4 h-4" /> {label}
                        </button>
                    ))}
                </div>
            )}

            {/* ═══ Deep Analysis Tab ═══ */}
            {activeTab === 'deep' && selectedArch && (
                <div className="space-y-6">
                    {/* Loading */}
                    {deepLoading && (
                        <div className="card p-16 flex flex-col items-center justify-center">
                            <div className="relative mb-6">
                                <div className="w-16 h-16 rounded-full border-4 border-indigo-100 border-t-indigo-600 animate-spin" />
                                <Network className="w-7 h-7 text-indigo-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                            </div>
                            <p className="text-gray-900 font-semibold mb-1">Running Deep Graph Analysis</p>
                            <p className="text-sm text-gray-400 text-center max-w-md">
                                Computing centrality, PageRank, clustering • Identifying interesting nodes •
                                Building context & narratives
                            </p>
                        </div>
                    )}

                    {/* Error */}
                    {deepError && (
                        <div className="card p-5 border-red-200 bg-red-50">
                            <div className="flex items-center gap-2 text-red-700 mb-2">
                                <XCircle className="w-5 h-5" />
                                <span className="font-bold text-sm">Analysis Failed</span>
                            </div>
                            <p className="text-xs text-red-600">{deepError}</p>
                            <button onClick={runDeepAnalysis} className="mt-3 text-xs text-blue-600 hover:text-blue-700 font-medium">Retry</button>
                        </div>
                    )}

                    {/* Report */}
                    {deepReport && (
                        <div className="space-y-6 animate-fade-in-up">
                            {/* Architecture banner */}
                            <div className="card overflow-hidden">
                                <div className="h-1.5 bg-gradient-to-r from-indigo-600 via-violet-600 to-cyan-600" />
                                <div className="p-6 flex items-center justify-between">
                                    <div>
                                        <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                            <Network className="w-5 h-5 text-indigo-600" />
                                            {deepReport.architecture_name || 'Architecture'}
                                        </h2>
                                        <p className="text-sm text-gray-500 mt-0.5">
                                            {deepReport.total_nodes} nodes • {deepReport.total_edges} edges •
                                            ${deepReport.total_cost.toLocaleString()}/mo •
                                            density {deepReport.graph_density} •
                                            {deepReport.components} component{deepReport.components !== 1 ? 's' : ''}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <button onClick={runDeepAnalysis} className="btn-outline px-3 py-2 text-sm flex items-center gap-1.5">
                                            <Zap className="w-3.5 h-3.5" /> Re-analyze
                                        </button>
                                        {!result && (
                                            <button onClick={runAgentAnalysis} disabled={loading} className="btn-primary px-4 py-2 text-sm flex items-center gap-1.5">
                                                <BrainCircuit className="w-3.5 h-3.5" /> Run AI Agents
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Summary dashboard */}
                            <DeepAnalysisSummary report={deepReport} />

                            {/* Per-node metrics table */}
                            <NodeMetricsTable
                                metrics={deepReport.all_node_metrics}
                                onSelectNode={handleSelectNode}
                            />

                            {/* Interesting Nodes */}
                            {deepReport.interesting_nodes?.length > 0 && (
                                <div>
                                    <div className="flex items-center gap-2 mb-4">
                                        <Target className="w-5 h-5 text-amber-600" />
                                        <h3 className="text-lg font-bold text-gray-900">
                                            Interesting Nodes ({deepReport.interesting_nodes.length})
                                        </h3>
                                        <span className="text-xs text-gray-400 ml-2">
                                            High centrality, high cost, many dependents, anomalies, or behavioral flags
                                        </span>
                                    </div>
                                    <div className="space-y-3">
                                        {deepReport.interesting_nodes.map(node => (
                                            <div key={node.node_id} ref={el => nodeRefs.current[node.node_id] = el}>
                                                <InterestingNodeCard
                                                    node={node}
                                                    isExpanded={!!expandedNodes[node.node_id]}
                                                    onToggle={() => setExpandedNodes(prev => ({
                                                        ...prev,
                                                        [node.node_id]: !prev[node.node_id],
                                                    }))}
                                                />
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ═══ Recommendation Cards Tab ═══ */}
            {activeTab === 'recommendations' && selectedArch && (
                <div className="space-y-6">
                    {/* Background refresh indicator - only show if refreshing and we have results */}
                    {recRefreshing && recResult && (
                        <div className="card p-3 bg-blue-50 border-blue-200 flex items-center gap-2">
                            <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                            <span className="text-xs text-blue-700">Refreshing recommendations in the background...</span>
                        </div>
                    )}

                    {/* Loading - only show if loading and no previous results */}
                    {recLoading && !recResult && (
                        <div className="card p-10 flex flex-col items-center justify-center">
                            <div className="relative mb-6">
                                <div className="w-16 h-16 rounded-full border-4 border-purple-100 border-t-purple-600 animate-spin" />
                                <Lightbulb className="w-7 h-7 text-purple-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                            </div>
                            <p className="text-gray-900 font-semibold mb-3">Discovering from CUR &amp; Generating Recommendations</p>
                            <div className="flex items-center gap-2 text-xs text-gray-500 mb-4">
                                {['Discovering from CUR', 'Graph Theory Analysis', 'Graph RAG Docs', 'LLM Recommendations'].map((step, i) => (
                                    <span key={i} className="flex items-center gap-1">
                                        <span className={`w-2 h-2 rounded-full ${i === 0 ? 'bg-emerald-500 animate-pulse' :
                                            i === 1 ? 'bg-blue-400 animate-pulse' :
                                                i === 2 ? 'bg-purple-400' : 'bg-gray-300'
                                            }`} />
                                        {step}
                                        {i < 3 && <span className="text-gray-300 mx-1">→</span>}
                                    </span>
                                ))}
                            </div>
                            <p className="text-[11px] text-gray-400 text-center max-w-lg">
                                8-section context package · Centrality &amp; PageRank analysis ·
                                Monte Carlo predictions · FinOps best practices from /docs ·
                                Strict 5-section recommendation cards
                            </p>
                        </div>
                    )}

                    {/* Error */}
                    {recError && (
                        <div className="card p-5 border-red-200 bg-red-50">
                            <div className="flex items-center gap-2 text-red-700 mb-2">
                                <XCircle className="w-5 h-5" />
                                <span className="font-bold text-sm">Recommendation Generation Failed</span>
                            </div>
                            <p className="text-sm text-red-600">{recError}</p>
                            <div className="mt-3 flex items-center gap-3">
                                <button onClick={runRecommendations} className="text-sm text-red-700 underline hover:text-red-900">Retry</button>
                                <button onClick={loadLastRecommendations} className="text-sm text-blue-600 underline hover:text-blue-800">Load last result from DB</button>
                            </div>
                        </div>
                    )}

                    {/* Results */}
                    {recResult && (
                        <div className="space-y-6">
                            {/* Summary bar */}
                            <div className="card p-5 bg-gradient-to-r from-purple-50 to-indigo-50 border-purple-200">
                                <div className="flex flex-col items-center justify-center gap-4 text-center">
                                    <div className="flex items-center gap-3 justify-center">
                                        <div className="w-10 h-10 rounded-lg bg-purple-100 border border-purple-200 flex items-center justify-center">
                                            <Lightbulb className="w-5 h-5 text-purple-600" />
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2 flex-wrap justify-center">
                                                <h3 className="text-base font-bold text-gray-900">
                                                    Optimization Recommendations
                                                </h3>
                                                <span className="inline-flex items-center justify-center min-w-9 h-9 px-3 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white text-sm font-black shadow-sm">
                                                    {displayRecommendations.length}
                                                </span>
                                            </div>
                                            <p className="text-xs text-gray-500">Action-ready AWS cost and risk optimization plan</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-center">
                                        <div className="text-center">
                                            <p className="text-[10px] text-gray-400 uppercase font-semibold">Total Potential Savings</p>
                                            <p className="text-2xl font-black text-emerald-600">
                                                ${displayedTotalSavings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<span className="text-sm text-gray-400 font-normal">/mo</span>
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-center">
                                        <button
                                            onClick={runRecommendations}
                                            disabled={recLoading}
                                            className="btn-secondary text-xs"
                                            title="Run a fresh Engine + LLM recommendation pipeline"
                                        >
                                            {recLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />} Run Fresh Engine + LLM
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* Recommendation Cards */}
                            <RecommendationCarousel 
                                recommendations={displayRecommendations}
                                onViewDetails={(rec) => {
                                    const recIdx = (displayRecommendations || []).findIndex(r => r === rec);
                                    if (recIdx >= 0) {
                                        setExpandedCards(prev => ({ ...prev, [recIdx]: true }));
                                        setTimeout(() => {
                                            document.querySelector(`[data-rec-id="${recIdx}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                                        }, 100);
                                    }
                                }}
                            />

                            {/* Recommendation Summary */}
                            {summaryDisplayLines.length > 0 && (
                                <div className="card p-6 border-indigo-200 bg-gradient-to-br from-slate-50 via-indigo-50/60 to-violet-50/70">
                                    <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
                                        <h4 className="text-sm font-bold text-gray-900">Recommendations Summary</h4>
                                        <span className="text-[11px] font-semibold text-indigo-700 bg-white border border-indigo-100 rounded-full px-2.5 py-1">
                                            {summaryDisplayLines.length} key actions
                                        </span>
                                    </div>
                                    <div className="rounded-xl border border-indigo-100 bg-white/70 backdrop-blur-sm p-4">
                                        <ol className="space-y-2">
                                            {summaryDisplayLines.map((line, idx) => (
                                                <li key={idx} className="text-sm text-gray-700 leading-relaxed">{line}</li>
                                            ))}
                                        </ol>
                                    </div>
                                </div>
                            )}

                            {/* Expanded Recommendation Details */}
                            {Object.keys(expandedCards).map(idx => expandedCards[idx] && (displayRecommendations || [])[idx]).filter(Boolean).map((card, cardIdx) => {
                                const originalIdx = (displayRecommendations || []).findIndex(r => r === card);
                                return (
                                    <div key={cardIdx} data-rec-id={originalIdx} className="mt-8">
                                        <div className="mb-4 flex items-center gap-2">
                                            <h3 className="text-lg font-bold text-gray-900">Recommendation Details</h3>
                                            <button 
                                                onClick={() => setExpandedCards(prev => ({ ...prev, [originalIdx]: false }))}
                                                className="ml-auto text-sm text-blue-600 hover:text-blue-800 underline"
                                            >
                                                Close
                                            </button>
                                        </div>
                                        <FullRecommendationCard
                                            card={card}
                                            index={originalIdx}
                                            isExpanded={true}
                                            onToggle={() => setExpandedCards(prev => ({ ...prev, [originalIdx]: !prev[originalIdx] }))}
                                        />
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* ═══ AI Agent Pipeline Tab ═══ */}
            {activeTab === 'agents' && selectedArch && (
                <div className="space-y-6">
                    {!result && !loading && (
                        <div className="card p-8 text-center">
                            <BrainCircuit className="w-12 h-12 text-gray-200 mx-auto mb-4" />
                            <h3 className="text-base font-bold text-gray-600 mb-2">Run 5-Agent AI Pipeline</h3>
                            <p className="text-sm text-gray-400 max-w-md mx-auto mb-6">
                                Monte Carlo simulation → Topology → Behavior → Cost → Detective → Synthesizer.
                                Uses GraphRAG grounding for zero-hallucination recommendations.
                            </p>
                            <button onClick={runAgentAnalysis} className="btn-primary px-6 py-3">
                                <BrainCircuit className="w-5 h-5" /> Start Analysis Pipeline
                            </button>
                        </div>
                    )}

                    {loading && (
                        <div className="card p-16 flex flex-col items-center justify-center">
                            <div className="relative mb-6">
                                <div className="w-16 h-16 rounded-full border-4 border-blue-100 border-t-blue-600 animate-spin" />
                                <BrainCircuit className="w-7 h-7 text-blue-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                            </div>
                            <p className="text-gray-900 font-semibold mb-1">Running FinOps-R1 Analysis Pipeline</p>
                            <p className="text-sm text-gray-400 text-center max-w-md">
                                Monte Carlo simulation → 5-agent analysis → GraphRAG-grounded reliable LLM report
                            </p>
                            <div className="mt-5 flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                                <div className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                                <div className="w-2 h-2 rounded-full bg-violet-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                        </div>
                    )}

                    {result && (
                        <div className="space-y-6 animate-fade-in-up">
                            {/* Verdict banner */}
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

                            {/* Root cause */}
                            {result.root_cause && (
                                <div className="card p-5 border-l-4 border-l-red-500 bg-red-50/30">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Target className="w-5 h-5 text-red-600" />
                                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider">Root Cause</h3>
                                    </div>
                                    <p className="text-sm text-gray-700 leading-relaxed">{result.root_cause}</p>
                                </div>
                            )}

                            {/* Pipeline + Recommendations */}
                            <div className="grid grid-cols-3 gap-6">
                                <div><AgentProgress agentResults={result.agents} timings={result.timings} /></div>
                                <div className="col-span-2">
                                    <div className="flex items-center gap-2 mb-4">
                                        <Sparkles className="w-5 h-5 text-violet-600" />
                                        <h3 className="text-lg font-bold text-gray-900">AI-Generated AWS Recommendations</h3>
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        {(result.recommendations || []).map((rec, i) => <RecommendationCard key={i} text={rec} index={i} />)}
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
                                                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${findingFilter === f ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}>
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

                    {/* LLM Report History Tab (within agents tab) */}
                    {result && (
                        <div className="mt-8 pt-8 border-t border-gray-200">
                            <div className="flex items-center justify-between mb-6">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-lg bg-indigo-100 border border-indigo-200 flex items-center justify-center">
                                        <History className="w-5 h-5 text-indigo-600" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold text-gray-900">LLM Report History</h3>
                                        <p className="text-sm text-gray-500">Previous 5-agent pipeline analyses</p>
                                    </div>
                                </div>
                                <button 
                                    onClick={loadLLMReportHistory}
                                    disabled={llmHistoryLoading}
                                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
                                >
                                    <Zap className="w-4 h-4" />
                                    {llmHistoryLoading ? 'Loading...' : 'Refresh'}
                                </button>
                            </div>

                            {llmHistoryError && (
                                <div className="card p-5 bg-red-50 border border-red-200 mb-4">
                                    <p className="text-sm text-red-700">{llmHistoryError}</p>
                                </div>
                            )}

                            {llmHistoryLoading && llmReportHistory.length === 0 ? (
                                <div className="card p-8 text-center">
                                    <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-3" />
                                    <p className="text-gray-600">Loading history...</p>
                                </div>
                            ) : llmReportHistory.length === 0 ? (
                                <div className="card p-8 text-center">
                                    <Clock className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                    <p className="text-gray-600">No previous analyses yet</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {llmReportHistory.map((report, idx) => (
                                        <div key={report.id || idx} className="card p-5 border-l-4 border-l-indigo-600 hover:shadow-md transition-all">
                                            <div className="flex items-start justify-between">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                                                            report.status === 'completed'
                                                                ? 'bg-emerald-100 text-emerald-700'
                                                                : 'bg-amber-100 text-amber-700'
                                                        }`}>
                                                            {report.status === 'completed' ? '✓ Completed' : `⚠ ${report.status}`}
                                                        </span>
                                                        <span className="text-xs text-gray-500">
                                                            {report.agent_names}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-gray-500 mb-2">
                                                        {new Date(report.created_at).toLocaleString('en-US', {
                                                            year: 'numeric',
                                                            month: 'short',
                                                            day: 'numeric',
                                                            hour: '2-digit',
                                                            minute: '2-digit'
                                                        })}
                                                    </p>
                                                    <div className="flex gap-4 text-sm">
                                                        <div className="flex items-center gap-1.5">
                                                            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                                                            <span className="text-gray-700">
                                                                <strong>{report.all_findings?.length || 0}</strong> findings
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <Clock className="w-3.5 h-3.5 text-gray-400" />
                                                            <span className="text-gray-700">
                                                                <strong>{((report.generation_time_ms || 0) / 1000).toFixed(1)}s</strong>
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ═══ Recommendation History Tab ═══ */}
            {activeTab === 'history' && selectedArch && (
                <div className="space-y-6">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-blue-100 border border-blue-200 flex items-center justify-center">
                                <History className="w-5 h-5 text-blue-600" />
                            </div>
                            <div>
                                <h2 className="text-lg font-bold text-gray-900">Recommendation History</h2>
                                <p className="text-sm text-gray-500">Previous recommendations for {selectedArch?.label}</p>
                            </div>
                        </div>
                        <button 
                            onClick={loadRecommendationHistory} 
                            disabled={historyLoading}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            <Zap className="w-4 h-4" /> 
                            {historyLoading ? 'Loading...' : 'Refresh'}
                        </button>
                    </div>

                    {/* Loading state */}
                    {historyLoading && !recHistory.length && (
                        <div className="card p-12 flex flex-col items-center justify-center">
                            <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-4" />
                            <p className="text-gray-600">Loading recommendation history...</p>
                        </div>
                    )}

                    {/* Error state */}
                    {historyError && (
                        <div className="card p-5 bg-red-50 border border-red-200 flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="text-sm font-semibold text-red-800">Failed to load history</p>
                                <p className="text-sm text-red-700 mt-1">{historyError}</p>
                            </div>
                        </div>
                    )}

                    {/* Empty state */}
                    {!historyLoading && recHistory.length === 0 && !historyError && (
                        <div className="card p-12 text-center">
                            <Clock className="w-12 h-12 text-gray-200 mx-auto mb-4" />
                            <h3 className="text-base font-bold text-gray-600 mb-2">No History Yet</h3>
                            <p className="text-sm text-gray-500 max-w-md mx-auto">Generate recommendations first to see history</p>
                        </div>
                    )}

                    {/* History Timeline */}
                    {!historyLoading && recHistory.length > 0 && (
                        <div className="space-y-6">
                            {/* List of snapshots */}
                            <div className="space-y-4">
                                {recHistory.map((item, idx) => (
                                    <div 
                                        key={item.id || idx} 
                                        onClick={() => setSelectedHistorySnapshot(item)}
                                        className={`card p-5 hover:shadow-md transition-all cursor-pointer border-l-4 ${
                                            selectedHistorySnapshot?.id === item.id
                                                ? 'border-l-indigo-600 bg-indigo-50 shadow-md'
                                                : 'border-l-blue-500 hover:bg-gray-50'
                                        }`}
                                    >
                                        {/* Header */}
                                        <div className="flex items-start justify-between mb-3">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <h3 className="font-semibold text-gray-900">
                                                        {item.architecture_name || 'Recommendation'}
                                                    </h3>
                                                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                                                        item.status === 'completed' 
                                                            ? 'bg-emerald-100 text-emerald-700' 
                                                            : 'bg-amber-100 text-amber-700'
                                                    }`}>
                                                        {item.status === 'completed' ? '✓ Completed' : `⚠ ${item.status}`}
                                                    </span>
                                                </div>
                                                <p className="text-xs text-gray-500">
                                                    {new Date(item.created_at).toLocaleString('en-US', { 
                                                        year: 'numeric',
                                                        month: 'short',
                                                        day: 'numeric',
                                                        hour: '2-digit',
                                                        minute: '2-digit',
                                                        second: '2-digit'
                                                    })}
                                                </p>
                                            </div>
                                            <div className="text-right flex-shrink-0">
                                                <div className="bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
                                                    <p className="text-xs text-emerald-600 font-semibold uppercase">Potential Savings</p>
                                                    <p className="text-lg font-bold text-emerald-700">
                                                        ${(item.total_estimated_savings || 0).toFixed(0)}/mo
                                                    </p>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Stats */}
                                        <div className="flex gap-4 mb-3 pb-3 border-b border-gray-200">
                                            <div className="flex items-center gap-2 text-sm">
                                                <Lightbulb className="w-4 h-4 text-indigo-500" />
                                                <span className="text-gray-700">
                                                    <strong>{item.card_count || 0}</strong> recommendations
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 text-sm">
                                                <Clock className="w-4 h-4 text-gray-400" />
                                                <span className="text-gray-700">
                                                    <strong>{((item.generation_time_ms || 0) / 1000).toFixed(1)}s</strong> to generate
                                                </span>
                                            </div>
                                            {item.llm_used && (
                                                <div className="flex items-center gap-2 text-sm">
                                                    <BrainCircuit className="w-4 h-4 text-blue-500" />
                                                    <span className="text-gray-700">LLM-Enhanced</span>
                                                </div>
                                            )}
                                        </div>

                                        {/* Recommendations Preview */}
                                        {item.recommendations?.length > 0 && (
                                            <div className="space-y-2">
                                                <p className="text-xs font-semibold text-gray-600 uppercase">Preview</p>
                                                <div className="space-y-1.5">
                                                    {item.recommendations.slice(0, 3).map((rec, i) => (
                                                        <div key={i} className="flex items-start gap-2 text-sm bg-gray-50 rounded p-2">
                                                            <span className="text-xs font-bold text-indigo-600 flex-shrink-0 mt-0.5">#{i + 1}</span>
                                                            <div className="flex-1 min-w-0">
                                                                <p className="text-gray-700 text-xs font-medium truncate">
                                                                    {rec.title || 'Cost Optimization'}
                                                                </p>
                                                                <p className="text-gray-500 text-xs">
                                                                    Saves ${(rec.total_estimated_savings || 0).toFixed(2)}/mo
                                                                </p>
                                                            </div>
                                                        </div>
                                                    ))}
                                                    {item.recommendations.length > 3 && (
                                                        <p className="text-xs text-gray-500 italic">
                                                            +{item.recommendations.length - 3} more recommendations
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {/* Error message if failed */}
                                        {item.error && (
                                            <div className="mt-3 p-2 bg-red-50 rounded border border-red-200">
                                                <p className="text-xs text-red-700">{item.error}</p>
                                            </div>
                                        )}

                                        {/* Click indicator */}
                                        {selectedHistorySnapshot?.id === item.id && (
                                            <div className="mt-3 pt-3 border-t border-indigo-200">
                                                <p className="text-xs text-indigo-600 font-semibold flex items-center gap-1">
                                                    <Eye className="w-3 h-3" /> Viewing full cards below
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>

                            {/* Selected snapshot cards display */}
                            {selectedHistorySnapshot && (
                                <div className="mt-8 pt-8 border-t border-gray-200">
                                    <div className="flex items-center justify-between mb-6">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-lg bg-indigo-100 border border-indigo-200 flex items-center justify-center">
                                                <Lightbulb className="w-5 h-5 text-indigo-600" />
                                            </div>
                                            <div>
                                                <h3 className="text-lg font-bold text-gray-900">Recommendation Cards</h3>
                                                <p className="text-sm text-gray-500">
                                                    {selectedHistorySnapshot.architecture_name || 'Snapshot'} • {new Date(selectedHistorySnapshot.created_at).toLocaleDateString()}
                                                </p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => setSelectedHistorySnapshot(null)}
                                            className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                                        >
                                            Close
                                        </button>
                                    </div>
                                    <RecommendationCarousel recommendations={selectedHistorySnapshot.recommendations || []} />
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Empty state */}
            {!selectedArch && !loading && !deepLoading && (
                <div className="card p-20 text-center">
                    <BrainCircuit className="w-16 h-16 text-gray-200 mx-auto mb-4" />
                    <h3 className="text-lg font-bold text-gray-400 mb-2">Select an AWS Architecture</h3>
                    <p className="text-sm text-gray-400 max-w-md mx-auto leading-relaxed">
                        Choose from the dropdown above. The deep graph analyzer will compute per-node
                        metrics, identify interesting nodes, and generate detailed narratives for
                        every node that needs attention.
                    </p>
                </div>
            )}
        </div>
    )

    function setTab(key) {
        setActiveTab(key)
        if (key === 'deep' && !deepReport && selectedArch) runDeepAnalysis()
        if (key === 'recommendations' && !recResult && selectedArch) runRecommendations()
        if (key === 'agents' && !result && selectedArch) runAgentAnalysis()
    }
}
