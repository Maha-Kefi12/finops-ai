import { useState, useEffect, useCallback, useRef } from 'react'
import {
    Layers, FileJson, GitBranch, BarChart3, Database, ArrowDown,
    CheckCircle2, Loader2, AlertCircle, Upload, Cloud, ChevronDown,
    Server, DollarSign, Activity, Zap, RefreshCw, Eye, Clock,
    Search, Network, FileText, ArrowRight, Shield, Box, Globe,
    XCircle, History, Code
} from 'lucide-react'
import {
    getSyntheticFiles, ingestBuiltinFile, ingestUploadedFile,
    ingestFromAws, getAwsPipelineStatus,
    listSnapshots, getGraphMetrics, listGraphs, getGraph
} from '../api/client'

/* ═══════════════════════════════════════════════════════════════════ */
/*  Constants                                                         */
/* ═══════════════════════════════════════════════════════════════════ */
const AWS_REGIONS = [
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
]

const AWS_STAGE_STEPS = [
    { key: 'queued',      label: 'Queued',     icon: Clock,        color: 'gray' },
    { key: 'discovery',   label: 'Discovery',  icon: Search,       color: 'blue' },
    { key: 'graph_build', label: 'Graph Build', icon: Network,     color: 'violet' },
    { key: 'storing',     label: 'Storage',    icon: Database,     color: 'indigo' },
    { key: 'completed',   label: 'Done',       icon: CheckCircle2, color: 'emerald' },
]

const STAGE_INDEX = {
    queued: 0,
    discovery: 1, discovery_done: 1,
    graph_build: 2, graph_done: 2,
    storing: 3, stored: 3,
    llm_report: 3, llm_done: 3,
    completed: 4,
    failed: -1,
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Shared UI                                                         */
/* ═══════════════════════════════════════════════════════════════════ */
function MetricPill({ label, value, color = 'blue' }) {
    return (
        <div className={`px-2.5 py-1.5 rounded-lg bg-${color}-50 border border-${color}-100`}>
            <p className="text-[10px] text-gray-400 uppercase">{label}</p>
            <p className={`text-sm font-bold text-${color}-700`}>{value}</p>
        </div>
    )
}

function Arrow() {
    return (
        <div className="flex justify-center py-1">
            <div className="flex flex-col items-center">
                <div className="w-px h-4 bg-gray-300" />
                <ArrowDown className="w-4 h-4 text-gray-400" />
            </div>
        </div>
    )
}

function StepCard({ step, title, desc, icon: Icon, color, status, children }) {
    const statusStyles = {
        idle:   'border-gray-200 bg-white',
        active: `border-${color}-300 bg-${color}-50/30 ring-2 ring-${color}-200`,
        done:   'border-emerald-300 bg-emerald-50/30',
        error:  'border-red-300 bg-red-50/30',
    }
    const statusBadge = {
        idle:   <span className="text-xs text-gray-400 font-medium">Waiting</span>,
        active: <span className="flex items-center gap-1 text-xs text-amber-600 font-medium"><Loader2 className="w-3 h-3 animate-spin" /> Processing</span>,
        done:   <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium"><CheckCircle2 className="w-3 h-3" /> Complete</span>,
        error:  <span className="flex items-center gap-1 text-xs text-red-600 font-medium"><AlertCircle className="w-3 h-3" /> Error</span>,
    }
    return (
        <div className={`card p-5 transition-all duration-300 ${statusStyles[status] || statusStyles.idle}`}>
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br from-${color}-500 to-${color}-600 flex items-center justify-center shadow-md`}>
                        <Icon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <span className={`text-[10px] font-bold uppercase text-${color}-600 tracking-wider`}>Layer {step}</span>
                        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
                    </div>
                </div>
                {statusBadge[status]}
            </div>
            <p className="text-xs text-gray-500 mb-3 leading-relaxed">{desc}</p>
            {children}
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  AWS Pipeline Track (no LLM stage)                                  */
/* ═══════════════════════════════════════════════════════════════════ */
function AWSPipelineTrack({ currentStage, detail, elapsed, totalServices, totalCost, rawJson, error }) {
    const currentStep = STAGE_INDEX[currentStage] ?? 0
    const isFailed = currentStage === 'failed'
    const isDone = currentStage === 'completed'
    const [showJson, setShowJson] = useState(false)

    return (
        <div className="card p-6 border-2 border-blue-200 bg-gradient-to-br from-slate-50 to-blue-50/30">
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2">
                    {isDone ? <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                     : isFailed ? <XCircle className="w-5 h-5 text-red-600" />
                     : <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />}
                    <span className={`text-sm font-bold ${isDone ? 'text-emerald-700' : isFailed ? 'text-red-700' : 'text-blue-700'}`}>
                        {isDone ? 'Ingestion Complete' : isFailed ? 'Ingestion Failed' : 'AWS Ingestion Pipeline'}
                    </span>
                </div>
                {elapsed > 0 && (
                    <span className="text-xs text-gray-500 font-mono bg-white px-2 py-1 rounded border border-gray-200">
                        {elapsed.toFixed(1)}s
                    </span>
                )}
            </div>

            <div className="flex items-center gap-0 mb-5">
                {AWS_STAGE_STEPS.map((step, i) => {
                    const Icon = step.icon
                    const isActive = !isFailed && i === currentStep
                    const isComplete = !isFailed && i < currentStep
                    let bg = 'bg-gray-100 border-gray-200 text-gray-400'
                    if (isComplete) bg = 'bg-emerald-100 border-emerald-300 text-emerald-600'
                    else if (isActive) bg = 'bg-blue-100 border-blue-400 text-blue-700 ring-2 ring-blue-200 shadow-sm'
                    else if (isFailed && i <= Math.abs(STAGE_INDEX[currentStage] ?? 0))
                        bg = 'bg-red-100 border-red-300 text-red-600'

                    return (
                        <div key={i} className="flex items-center flex-1">
                            <div className="flex flex-col items-center gap-1.5 flex-1">
                                <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${bg}`}>
                                    {isComplete ? <CheckCircle2 className="w-4 h-4" />
                                     : isActive ? <Loader2 className="w-4 h-4 animate-spin" />
                                     : <Icon className="w-4 h-4" />}
                                </div>
                                <span className={`text-[10px] font-medium ${isActive ? 'text-blue-700' : isComplete ? 'text-emerald-600' : 'text-gray-400'}`}>
                                    {step.label}
                                </span>
                            </div>
                            {i < AWS_STAGE_STEPS.length - 1 && (
                                <div className={`h-0.5 w-full -mt-4 transition-all duration-500 ${isComplete ? 'bg-emerald-400' : 'bg-gray-200'}`} />
                            )}
                        </div>
                    )
                })}
            </div>

            {detail && (
                <div className={`rounded-lg px-4 py-2.5 text-sm flex items-center gap-2 ${isFailed ? 'bg-red-50 text-red-700 border border-red-200' : isDone ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-white text-gray-700 border border-gray-200'}`}>
                    {!isDone && !isFailed && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />}
                    {detail}
                </div>
            )}

            {isDone && (totalServices > 0 || totalCost > 0) && (
                <div className="grid grid-cols-3 gap-3 mt-4">
                    <div className="bg-white rounded-lg p-3 border border-emerald-200 shadow-sm">
                        <p className="text-xs text-gray-500 flex items-center gap-1"><Server className="w-3 h-3" /> Resources</p>
                        <p className="text-lg font-bold text-gray-900">{totalServices}</p>
                    </div>
                    <div className="bg-white rounded-lg p-3 border border-emerald-200 shadow-sm">
                        <p className="text-xs text-gray-500 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Monthly Cost</p>
                        <p className="text-lg font-bold text-gray-900">${(totalCost || 0).toLocaleString()}</p>
                    </div>
                    <div className="bg-white rounded-lg p-3 border border-emerald-200 shadow-sm">
                        <p className="text-xs text-gray-500 flex items-center gap-1"><Clock className="w-3 h-3" /> Duration</p>
                        <p className="text-lg font-bold text-gray-900">{elapsed.toFixed(1)}s</p>
                    </div>
                </div>
            )}

            {/* Raw JSON output toggle */}
            {isDone && rawJson && (
                <div className="mt-4">
                    <button onClick={() => setShowJson(!showJson)}
                        className="flex items-center gap-2 text-xs font-medium text-blue-600 hover:text-blue-700 mb-2">
                        <Code className="w-3.5 h-3.5" />
                        {showJson ? 'Hide' : 'Show'} Raw JSON Output
                    </button>
                    {showJson && (
                        <div className="bg-gray-900 text-green-400 rounded-lg p-4 max-h-96 overflow-auto text-xs font-mono leading-relaxed border border-gray-700">
                            <pre>{JSON.stringify(rawJson, null, 2)}</pre>
                        </div>
                    )}
                </div>
            )}

            {isFailed && error && (
                <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-3">
                    <p className="text-xs font-bold text-red-700 mb-1">Error Details</p>
                    <p className="text-xs text-red-600 font-mono break-all">{error}</p>
                    <p className="text-xs text-gray-500 mt-2">Check AWS credentials in .env (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY).</p>
                </div>
            )}
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  MAIN PAGE                                                         */
/* ═══════════════════════════════════════════════════════════════════ */
export default function PipelinePage() {
    const [tab, setTab] = useState('aws')
    const [error, setError] = useState(null)
    const [snapshots, setSnapshots] = useState([])
    const [snapshotsLoading, setSnapshotsLoading] = useState(false)

    /* AWS pipeline */
    const [awsRegion, setAwsRegion] = useState('us-east-1')
    const [pipelineRunning, setPipelineRunning] = useState(false)
    const [pipelineSnapshotId, setPipelineSnapshotId] = useState(null)
    const [pipelineStatus, setPipelineStatus] = useState(null)
    const [pipelineElapsed, setPipelineElapsed] = useState(0)
    const [awsRawJson, setAwsRawJson] = useState(null)
    const pollRef = useRef(null)
    const startTimeRef = useRef(null)
    const timerRef = useRef(null)

    /* File pipeline */
    const [syntheticFiles, setSyntheticFiles] = useState([])
    const [selectedFile, setSelectedFile] = useState(null)
    const [dropdown, setDropdown] = useState(false)
    const [filePipelineState, setFilePipelineState] = useState('idle')
    const [rawData, setRawData] = useState(null)
    const [graphInfo, setGraphInfo] = useState(null)
    const [metricsData, setMetricsData] = useState(null)
    const [storageResult, setStorageResult] = useState(null)
    const [fileElapsed, setFileElapsed] = useState(0)
    const [dragging, setDragging] = useState(false)
    const [fileRawJson, setFileRawJson] = useState(null)
    const [showFileJson, setShowFileJson] = useState(false)

    useEffect(() => {
        getSyntheticFiles().then(r => setSyntheticFiles(r.data.files || [])).catch(() => {})
        loadSnapshots()
        return () => {
            if (pollRef.current) clearInterval(pollRef.current)
            if (timerRef.current) clearInterval(timerRef.current)
        }
    }, [])

    useEffect(() => {
        if (filePipelineState !== 'idle' && filePipelineState !== 'done' && filePipelineState !== 'error') {
            const t = setInterval(() => setFileElapsed(e => e + 0.1), 100)
            return () => clearInterval(t)
        }
    }, [filePipelineState])

    const loadSnapshots = () => {
        setSnapshotsLoading(true)
        listSnapshots().then(r => setSnapshots(r.data.snapshots || [])).catch(() => {}).finally(() => setSnapshotsLoading(false))
    }

    const getFileStepStatus = (step) => {
        const order = ['idle', 'ingesting', 'building', 'computing', 'storing', 'done']
        const stepMap = { 1: 'ingesting', 2: 'building', 3: 'computing', 4: 'storing' }
        const idx = order.indexOf(filePipelineState)
        const stepIdx = order.indexOf(stepMap[step])
        if (filePipelineState === 'error') return idx >= stepIdx ? 'error' : 'idle'
        if (idx > stepIdx) return 'done'
        if (idx === stepIdx) return 'active'
        return 'idle'
    }

    /* ── AWS Pipeline ─────────────────────────────────────────────── */
    const startAwsPipeline = async () => {
        setError(null)
        setPipelineRunning(true)
        setPipelineStatus(null)
        setPipelineElapsed(0)
        setAwsRawJson(null)
        startTimeRef.current = Date.now()
        timerRef.current = setInterval(() => {
            setPipelineElapsed((Date.now() - startTimeRef.current) / 1000)
        }, 500)

        try {
            const res = await ingestFromAws(awsRegion)
            const snapId = res.data.snapshot_id
            setPipelineSnapshotId(snapId)
            setPipelineStatus({ status: 'running', pipeline_stage: 'queued', pipeline_detail: 'Pipeline started, queuing discovery...' })

            pollRef.current = setInterval(async () => {
                try {
                    const statusRes = await getAwsPipelineStatus(snapId)
                    const data = statusRes.data
                    setPipelineStatus(data)
                    if (data.status === 'completed' || data.status === 'failed') {
                        clearInterval(pollRef.current); clearInterval(timerRef.current)
                        pollRef.current = null; timerRef.current = null
                        setPipelineRunning(false)
                        if (data.duration_seconds > 0) setPipelineElapsed(data.duration_seconds)
                        // Build raw JSON summary for output
                        setAwsRawJson({
                            snapshot_id: snapId,
                            status: data.status,
                            region: awsRegion,
                            total_services: data.total_services,
                            total_cost_monthly: data.total_cost_monthly,
                            duration_seconds: data.duration_seconds,
                            pipeline_stages: ['discovery', 'graph_build', 'storing', 'completed'],
                        })
                        loadSnapshots()
                    }
                } catch { /* transient */ }
            }, 1500)
        } catch (e) {
            clearInterval(timerRef.current); timerRef.current = null
            setPipelineRunning(false)
            const detail = e.response?.data?.detail
            const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ') : e.message
            setError(msg)
            setPipelineStatus({ status: 'failed', pipeline_stage: 'failed', pipeline_detail: msg, error_message: msg })
        }
    }

    const resetAwsPipeline = () => { setPipelineStatus(null); setPipelineSnapshotId(null); setPipelineElapsed(0); setError(null); setAwsRawJson(null) }

    /* ── File Pipeline ────────────────────────────────────────────── */
    const runFilePipeline = async (filename) => {
        setError(null); setRawData(null); setGraphInfo(null); setMetricsData(null); setStorageResult(null); setFileElapsed(0); setFileRawJson(null)
        try {
            setFilePipelineState('ingesting'); await new Promise(r => setTimeout(r, 300))
            setFilePipelineState('building')
            const result = await ingestBuiltinFile(filename)
            const res = result.data
            setRawData({ services: res.total_services, name: res.name, pattern: res.pattern })
            setFilePipelineState('computing'); await new Promise(r => setTimeout(r, 200))
            const archId = res.id
            let graphData = null, metricsResult = null
            try {
                const graphRes = await getGraph(archId)
                const metricsRes = await getGraphMetrics(archId)
                if (graphRes?.data) {
                    graphData = graphRes.data
                    const gd = graphRes.data
                    setGraphInfo({ nodes: gd.nodes?.length || 0, edges: gd.links?.length || 0, density: gd.metrics?.density || 0, isDAG: gd.metrics?.is_dag, components: gd.metrics?.components || 0 })
                }
                if (metricsRes?.data?.metrics) { metricsResult = metricsRes.data.metrics; setMetricsData(metricsRes.data.metrics) }
            } catch {}
            setFilePipelineState('storing'); await new Promise(r => setTimeout(r, 200))
            setStorageResult({ archId, name: res.name, cost: res.total_cost_monthly })
            // Build raw JSON output
            setFileRawJson({
                id: archId, name: res.name, pattern: res.pattern,
                total_services: res.total_services,
                total_cost_monthly: res.total_cost_monthly,
                graph: graphData ? { nodes: graphData.nodes?.length || 0, edges: graphData.links?.length || 0, density: graphData.metrics?.density, is_dag: graphData.metrics?.is_dag } : null,
                metrics_summary: metricsResult ? { top_bottlenecks: metricsResult.centrality?.top_bottlenecks?.slice(0, 3) || [], top_pagerank: metricsResult.pagerank?.top_important?.slice(0, 3) || [] } : null,
            })
            setFilePipelineState('done'); loadSnapshots()
        } catch (err) {
            const detail = err.response?.data?.detail
            const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ') : err.message
            setError(msg); setFilePipelineState('error')
        }
    }

    const handleFileIngest = (filename) => { setSelectedFile(filename); setDropdown(false); runFilePipeline(filename) }

    const handleUpload = async (file) => {
        if (!file) return
        setSelectedFile(file.name); setError(null); setRawData(null); setGraphInfo(null); setMetricsData(null); setStorageResult(null); setFileElapsed(0); setFileRawJson(null)
        try {
            setFilePipelineState('ingesting'); await new Promise(r => setTimeout(r, 300))
            setFilePipelineState('building')
            const result = await ingestUploadedFile(file)
            const res = result.data
            setRawData({ services: res.total_services, name: res.name, pattern: res.pattern })
            setFilePipelineState('computing'); await new Promise(r => setTimeout(r, 200))
            const archId = res.id
            try {
                const graphRes = await getGraph(archId)
                const metricsRes = await getGraphMetrics(archId)
                if (graphRes?.data) {
                    const gd = graphRes.data
                    setGraphInfo({ nodes: gd.nodes?.length || 0, edges: gd.links?.length || 0, density: gd.metrics?.density || 0, isDAG: gd.metrics?.is_dag, components: gd.metrics?.components || 0 })
                }
                if (metricsRes?.data?.metrics) setMetricsData(metricsRes.data.metrics)
            } catch {}
            setFilePipelineState('storing'); await new Promise(r => setTimeout(r, 200))
            setStorageResult({ archId, name: res.name, cost: res.total_cost_monthly })
            setFileRawJson({ id: archId, name: res.name, pattern: res.pattern, total_services: res.total_services, total_cost_monthly: res.total_cost_monthly })
            setFilePipelineState('done'); loadSnapshots()
        } catch (err) {
            const detail = err.response?.data?.detail
            const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ') : err.message
            setError(msg); setFilePipelineState('error')
        }
    }

    const resetFilePipeline = () => { setFilePipelineState('idle'); setSelectedFile(null); setRawData(null); setGraphInfo(null); setMetricsData(null); setStorageResult(null); setError(null); setFileElapsed(0); setFileRawJson(null) }

    const onDrop = useCallback((e) => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files?.[0]; if (file) handleUpload(file) }, [])

    /* ═══════════════════════════════════════════════════════════════ */
    const tabs = [
        { key: 'aws',       label: 'Ingest Now (AWS)',  icon: Cloud },
        { key: 'synthetic', label: 'Synthetic Data',    icon: FileJson },
        { key: 'upload',    label: 'Upload JSON',       icon: Upload },
        { key: 'history',   label: 'Snapshots',         icon: History },
    ]

    return (
        <div className="max-w-5xl mx-auto px-6 py-10 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
                        <Layers className="w-8 h-8 text-indigo-600" />
                        Ingestion Pipeline
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        Ingest AWS infrastructure or load synthetic JSON — watch it flow through Discovery → Graph Build → Storage
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400 font-medium">{snapshots.length} snapshots</span>
                    <button onClick={loadSnapshots} className="btn-outline px-3 py-2">
                        <RefreshCw className={`w-4 h-4 ${snapshotsLoading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 p-1 bg-gray-100 rounded-xl border border-gray-200 w-fit">
                {tabs.map(({ key, label, icon: Icon }) => (
                    <button key={key} onClick={() => setTab(key)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${tab === key ? 'bg-white text-blue-700 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-700 hover:bg-white/50'}`}>
                        <Icon className="w-4 h-4" /> {label}
                    </button>
                ))}
            </div>

            {error && !pipelineStatus && filePipelineState !== 'error' && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                </div>
            )}

            {/* ═════ TAB: AWS LIVE ═════ */}
            {tab === 'aws' && (
                <div className="space-y-5">
                    <div className="card p-6 border-2 border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50">
                        <div className="flex items-start gap-5">
                            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center flex-shrink-0 shadow-lg">
                                <Cloud className="w-7 h-7 text-white" />
                            </div>
                            <div className="flex-1">
                                <h2 className="text-lg font-bold text-gray-900 mb-1">Ingest Now — Full AWS Discovery</h2>
                                <p className="text-sm text-gray-600 mb-4">
                                    Discover VPCs, Subnets, EC2, ECS, RDS, S3, ALBs, Security Groups, IAM, CloudWatch, SSM —
                                    detect all dependencies and build the full infrastructure graph.
                                </p>
                                <div className="flex items-end gap-4">
                                    <div>
                                        <label className="block text-xs text-gray-500 mb-1.5 font-medium">AWS Region</label>
                                        <select value={awsRegion} onChange={e => setAwsRegion(e.target.value)} disabled={pipelineRunning}
                                            className="bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200 disabled:opacity-50">
                                            {AWS_REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
                                        </select>
                                    </div>
                                    <button onClick={startAwsPipeline} disabled={pipelineRunning}
                                        className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white font-bold rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed">
                                        {pipelineRunning ? <><Loader2 className="w-5 h-5 animate-spin" /> Pipeline Running...</> : <><Zap className="w-5 h-5" /> Ingest Now</>}
                                    </button>
                                    {pipelineStatus && !pipelineRunning && (
                                        <button onClick={resetAwsPipeline} className="btn-outline px-3 py-2 text-sm"><RefreshCw className="w-4 h-4" /> Run Again</button>
                                    )}
                                </div>
                                <div className="mt-3 flex items-center gap-3 text-xs text-gray-500 flex-wrap">
                                    <span className="flex items-center gap-1"><Server className="w-3 h-3" /> EC2 + ECS + RDS</span>
                                    <span className="flex items-center gap-1"><Globe className="w-3 h-3" /> VPC + Subnets + ALB</span>
                                    <span className="flex items-center gap-1"><Shield className="w-3 h-3" /> Security Groups + IAM</span>
                                    <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" /> Cost Explorer</span>
                                    <span className="flex items-center gap-1"><Database className="w-3 h-3" /> Graph Storage</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {pipelineStatus && (
                        <AWSPipelineTrack
                            currentStage={pipelineStatus.pipeline_stage || 'queued'}
                            detail={pipelineStatus.pipeline_detail || ''}
                            elapsed={pipelineElapsed}
                            totalServices={pipelineStatus.total_services || 0}
                            totalCost={pipelineStatus.total_cost_monthly || 0}
                            rawJson={awsRawJson}
                            error={pipelineStatus.error_message}
                        />
                    )}

                    {!pipelineStatus && (
                        <div className="card p-6">
                            <h3 className="text-sm font-bold text-gray-900 mb-4">How the Ingestion Pipeline Works</h3>
                            <div className="grid grid-cols-4 gap-3">
                                {[
                                    { step: 1, title: 'Discovery',    desc: 'VPC, EC2, ECS, RDS, S3, ALB, IAM, SG, CW', icon: Search,   color: 'blue' },
                                    { step: 2, title: 'Dependencies', desc: 'Subnet→VPC, EC2→SG, ECS→ALB relationships', icon: Network,  color: 'violet' },
                                    { step: 3, title: 'Graph Build',  desc: 'NetworkX DiGraph + centrality metrics',     icon: Box,      color: 'indigo' },
                                    { step: 4, title: 'Storage',      desc: 'PostgreSQL: architectures, services, deps', icon: Database, color: 'amber' },
                                ].map(({ step, title, desc, icon: Icon, color }, i) => (
                                    <div key={step} className="relative">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className={`w-8 h-8 rounded-lg bg-${color}-50 flex items-center justify-center text-${color}-600 border border-${color}-200`}>
                                                <Icon className="w-4 h-4" />
                                            </div>
                                            {i < 3 && <ArrowRight className="w-4 h-4 text-gray-300 flex-shrink-0" />}
                                        </div>
                                        <h4 className={`text-xs font-bold text-${color}-600 mb-0.5`}>{title}</h4>
                                        <p className="text-[11px] text-gray-500 leading-relaxed">{desc}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ═════ TAB: SYNTHETIC ═════ */}
            {tab === 'synthetic' && (
                <div className="space-y-6">
                    <div className="card p-5 border-2 border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-violet-50/50">
                        <h2 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                            <FileJson className="w-4 h-4 text-indigo-600" /> Select Synthetic File & Run Pipeline
                        </h2>
                        <div className="flex items-center gap-4">
                            <div className="relative flex-1">
                                <button onClick={() => setDropdown(!dropdown)}
                                    disabled={filePipelineState !== 'idle' && filePipelineState !== 'done' && filePipelineState !== 'error'}
                                    className="w-full flex items-center justify-between px-4 py-2.5 bg-white border border-gray-300 rounded-lg text-sm text-gray-700 hover:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:opacity-50">
                                    <span>{selectedFile || 'Choose a synthetic JSON file...'}</span>
                                    <ChevronDown className="w-4 h-4 text-gray-400" />
                                </button>
                                {dropdown && (
                                    <div className="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-30 max-h-64 overflow-y-auto">
                                        {syntheticFiles.map(f => (
                                            <button key={f.filename} onClick={() => handleFileIngest(f.filename)}
                                                className="w-full text-left px-3 py-2 rounded-lg text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex justify-between">
                                                <span className="truncate">{f.name || f.filename}</span>
                                                <span className="text-xs text-gray-400 ml-2 flex-shrink-0">{f.total_services} svc</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {filePipelineState !== 'idle' && (
                                <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-lg">
                                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                                    <span className="text-xs font-mono text-gray-600">{fileElapsed.toFixed(1)}s</span>
                                </div>
                            )}
                            {(filePipelineState === 'done' || filePipelineState === 'error') && (
                                <button onClick={resetFilePipeline} className="btn-outline px-3 py-2 text-sm"><RefreshCw className="w-4 h-4" /> Run Again</button>
                            )}
                        </div>
                    </div>

                    {error && filePipelineState === 'error' && (
                        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                        </div>
                    )}

                    <StepCard step={1} title="Raw JSON Ingestion" icon={FileJson} color="blue"
                        desc="Parse the raw JSON file containing services and dependencies arrays." status={getFileStepStatus(1)}>
                        {rawData && (
                            <div className="grid grid-cols-3 gap-2 mt-2">
                                <MetricPill label="Architecture" value={rawData.name} color="blue" />
                                <MetricPill label="Pattern" value={rawData.pattern} color="blue" />
                                <MetricPill label="Services" value={rawData.services} color="blue" />
                            </div>
                        )}
                    </StepCard>
                    <Arrow />
                    <StepCard step={2} title="Graph Engine (NetworkX)" icon={GitBranch} color="violet"
                        desc="Build a directed graph: Nodes = Services, Edges = Dependencies." status={getFileStepStatus(2)}>
                        {graphInfo && (
                            <div className="grid grid-cols-5 gap-2 mt-2">
                                <MetricPill label="Nodes" value={graphInfo.nodes} color="violet" />
                                <MetricPill label="Edges" value={graphInfo.edges} color="violet" />
                                <MetricPill label="Density" value={graphInfo.density.toFixed(4)} color="violet" />
                                <MetricPill label="Components" value={graphInfo.components} color="violet" />
                                <MetricPill label="DAG" value={graphInfo.isDAG ? 'Yes' : 'No'} color="violet" />
                            </div>
                        )}
                    </StepCard>
                    <Arrow />
                    <StepCard step={3} title="Graph Metrics Calculated" icon={BarChart3} color="amber"
                        desc="Compute centrality, PageRank, and clustering for every node." status={getFileStepStatus(3)}>
                        {metricsData && (
                            <div className="space-y-3 mt-2">
                                <div className="p-3 bg-orange-50 border border-orange-100 rounded-lg">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Activity className="w-3.5 h-3.5 text-orange-600" />
                                        <span className="text-xs font-bold text-orange-700">Centrality — Bottlenecks</span>
                                    </div>
                                    {metricsData.centrality?.top_bottlenecks?.length > 0 ? (
                                        <div className="space-y-1">
                                            {metricsData.centrality.top_bottlenecks.slice(0, 5).map(([node, score], i) => (
                                                <div key={node} className="flex items-center gap-2">
                                                    <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${i === 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>{i + 1}</span>
                                                    <span className="text-xs text-gray-700 font-medium flex-1 truncate">{node}</span>
                                                    <div className="flex-1 max-w-[120px]"><div className="h-1.5 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-orange-500 rounded-full" style={{ width: `${Math.min(score * 100 / 0.5, 100)}%` }} /></div></div>
                                                    <span className="text-[10px] text-gray-500 font-mono w-12 text-right">{score.toFixed(4)}</span>
                                                </div>
                                            ))}
                                        </div>
                                    ) : <p className="text-xs text-gray-500">No betweenness centrality data</p>}
                                </div>
                                <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Zap className="w-3.5 h-3.5 text-blue-600" />
                                        <span className="text-xs font-bold text-blue-700">PageRank — Most Important</span>
                                    </div>
                                    {metricsData.pagerank?.top_important?.length > 0 ? (
                                        <div className="space-y-1">
                                            {metricsData.pagerank.top_important.slice(0, 5).map(([node, score], i) => (
                                                <div key={node} className="flex items-center gap-2">
                                                    <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${i === 0 ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>{i + 1}</span>
                                                    <span className="text-xs text-gray-700 font-medium flex-1 truncate">{node}</span>
                                                    <div className="flex-1 max-w-[120px]"><div className="h-1.5 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(score * 100 / 0.15, 100)}%` }} /></div></div>
                                                    <span className="text-[10px] text-gray-500 font-mono w-12 text-right">{score.toFixed(4)}</span>
                                                </div>
                                            ))}
                                        </div>
                                    ) : <p className="text-xs text-gray-500">No PageRank data</p>}
                                </div>
                                <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Server className="w-3.5 h-3.5 text-emerald-600" />
                                        <span className="text-xs font-bold text-emerald-700">Clustering — Cohesion</span>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2">
                                        <MetricPill label="Density" value={metricsData.clustering?.density?.toFixed(4) || '0'} color="emerald" />
                                        <MetricPill label="Components" value={metricsData.clustering?.n_components || 0} color="emerald" />
                                        <MetricPill label="DAG" value={metricsData.clustering?.is_dag ? 'Yes' : 'No'} color="emerald" />
                                    </div>
                                </div>
                            </div>
                        )}
                    </StepCard>
                    <Arrow />
                    <StepCard step={4} title="Stored in Database" icon={Database} color="emerald"
                        desc="Persist graph, per-node metrics, services, dependencies, ingestion snapshot to PostgreSQL." status={getFileStepStatus(4)}>
                        {storageResult && (
                            <div className="space-y-3 mt-2">
                                <div className="grid grid-cols-3 gap-2">
                                    <MetricPill label="Arch ID" value={storageResult.archId?.slice(0, 8) + '...'} color="emerald" />
                                    <MetricPill label="Name" value={storageResult.name} color="emerald" />
                                    <MetricPill label="Monthly Cost" value={`$${(storageResult.cost || 0).toLocaleString()}`} color="emerald" />
                                </div>
                                <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg">
                                    <p className="text-xs text-emerald-700"><strong>Tables written:</strong> architectures, services, dependencies, graph_metrics, ingestion_snapshots</p>
                                </div>
                            </div>
                        )}
                    </StepCard>

                    {filePipelineState === 'done' && (
                        <>
                            <div className="flex items-center justify-center gap-3 py-4">
                                <div className="h-px flex-1 bg-emerald-200" />
                                <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 border border-emerald-200 rounded-full">
                                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                    <span className="text-sm font-bold text-emerald-700">Pipeline Complete</span>
                                    <span className="text-xs text-gray-500">({fileElapsed.toFixed(1)}s)</span>
                                </div>
                                <div className="h-px flex-1 bg-emerald-200" />
                            </div>
                            {fileRawJson && (
                                <div className="card p-4">
                                    <button onClick={() => setShowFileJson(!showFileJson)}
                                        className="flex items-center gap-2 text-xs font-medium text-blue-600 hover:text-blue-700 mb-2">
                                        <Code className="w-3.5 h-3.5" />
                                        {showFileJson ? 'Hide' : 'Show'} Raw JSON Output
                                    </button>
                                    {showFileJson && (
                                        <div className="bg-gray-900 text-green-400 rounded-lg p-4 max-h-96 overflow-auto text-xs font-mono leading-relaxed border border-gray-700">
                                            <pre>{JSON.stringify(fileRawJson, null, 2)}</pre>
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* ═════ TAB: UPLOAD ═════ */}
            {tab === 'upload' && (
                <div className="space-y-6">
                    <div
                        onDragOver={e => { e.preventDefault(); setDragging(true) }}
                        onDragLeave={() => setDragging(false)}
                        onDrop={onDrop}
                        className={`relative card flex flex-col items-center justify-center gap-4 p-12 text-center cursor-pointer transition-all duration-200 border-2 border-dashed
                            ${dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-300 hover:bg-gray-50'}`}
                        onClick={() => document.getElementById('pipeline-file-input').click()}>
                        <input id="pipeline-file-input" type="file" accept=".json" className="hidden"
                            onChange={e => handleUpload(e.target.files?.[0])} />
                        <Upload className={`w-12 h-12 ${dragging ? 'text-blue-500' : 'text-gray-300'}`} />
                        <div>
                            <p className="text-sm font-medium text-gray-700">{dragging ? 'Drop to upload & ingest' : 'Drag & drop a JSON file or click to browse'}</p>
                            <p className="text-xs text-gray-400 mt-1">Must follow the architecture schema (metadata + services + dependencies)</p>
                        </div>
                    </div>

                    {filePipelineState !== 'idle' && (
                        <>
                            <StepCard step={1} title="Raw JSON Ingestion" icon={FileJson} color="blue"
                                desc="Parse and validate the uploaded JSON." status={getFileStepStatus(1)}>
                                {rawData && (
                                    <div className="grid grid-cols-3 gap-2 mt-2">
                                        <MetricPill label="Architecture" value={rawData.name} color="blue" />
                                        <MetricPill label="Pattern" value={rawData.pattern} color="blue" />
                                        <MetricPill label="Services" value={rawData.services} color="blue" />
                                    </div>
                                )}
                            </StepCard>
                            <Arrow />
                            <StepCard step={2} title="Graph Engine" icon={GitBranch} color="violet"
                                desc="Build NetworkX DiGraph." status={getFileStepStatus(2)}>
                                {graphInfo && (
                                    <div className="grid grid-cols-5 gap-2 mt-2">
                                        <MetricPill label="Nodes" value={graphInfo.nodes} color="violet" />
                                        <MetricPill label="Edges" value={graphInfo.edges} color="violet" />
                                        <MetricPill label="Density" value={graphInfo.density.toFixed(4)} color="violet" />
                                        <MetricPill label="Components" value={graphInfo.components} color="violet" />
                                        <MetricPill label="DAG" value={graphInfo.isDAG ? 'Yes' : 'No'} color="violet" />
                                    </div>
                                )}
                            </StepCard>
                            <Arrow />
                            <StepCard step={3} title="Graph Metrics" icon={BarChart3} color="amber"
                                desc="Centrality, PageRank, clustering." status={getFileStepStatus(3)} />
                            <Arrow />
                            <StepCard step={4} title="Stored" icon={Database} color="emerald"
                                desc="Persisted to PostgreSQL." status={getFileStepStatus(4)}>
                                {storageResult && (
                                    <div className="grid grid-cols-3 gap-2 mt-2">
                                        <MetricPill label="Arch ID" value={storageResult.archId?.slice(0, 8) + '...'} color="emerald" />
                                        <MetricPill label="Name" value={storageResult.name} color="emerald" />
                                        <MetricPill label="Cost" value={`$${(storageResult.cost || 0).toLocaleString()}`} color="emerald" />
                                    </div>
                                )}
                            </StepCard>
                            {filePipelineState === 'done' && (
                                <div className="flex items-center justify-center gap-3 py-2">
                                    <div className="h-px flex-1 bg-emerald-200" />
                                    <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 border border-emerald-200 rounded-full">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                        <span className="text-sm font-bold text-emerald-700">Pipeline Complete</span>
                                        <span className="text-xs text-gray-500">({fileElapsed.toFixed(1)}s)</span>
                                    </div>
                                    <div className="h-px flex-1 bg-emerald-200" />
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* ═════ TAB: SNAPSHOTS ═════ */}
            {tab === 'history' && (
                <div>
                    <h2 className="text-base font-semibold text-gray-900 mb-4">
                        Ingestion Snapshots <span className="ml-2 text-xs font-normal text-gray-400">({snapshots.length} total)</span>
                    </h2>
                    {snapshots.length === 0 ? (
                        <div className="card p-12 flex flex-col items-center gap-3 text-gray-400">
                            <History className="w-12 h-12" /> <p className="text-sm">No ingestion snapshots yet.</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {snapshots.map(s => (
                                <div key={s.id} className="card p-4 flex items-center gap-4 hover:border-blue-200 hover:shadow-sm transition-all duration-200">
                                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${s.source === 'aws' ? 'bg-amber-50 border border-amber-200' : 'bg-blue-50 border border-blue-200'}`}>
                                        {s.source === 'aws' ? <Cloud className="w-5 h-5 text-amber-600" /> : <FileJson className="w-5 h-5 text-blue-600" />}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <p className="text-sm font-semibold text-gray-900 truncate">{s.source === 'aws' ? `AWS Live (${s.region})` : 'File Ingestion'}</p>
                                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${s.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : s.status === 'running' ? 'bg-amber-50 text-amber-700 border border-amber-200' : s.status === 'failed' ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-gray-50 text-gray-600 border border-gray-200'}`}>
                                                {s.status === 'completed' ? <CheckCircle2 className="w-3 h-3" /> : s.status === 'running' ? <Loader2 className="w-3 h-3 animate-spin" /> : s.status === 'failed' ? <XCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                                                {s.status}
                                            </span>
                                            {s.pipeline_stage && s.status === 'running' && (
                                                <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">{s.pipeline_stage}</span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {s.created_at ? new Date(s.created_at).toLocaleString() : 'N/A'}</span>
                                            {s.total_services > 0 && <span className="flex items-center gap-1"><Server className="w-3 h-3" /> {s.total_services} svc</span>}
                                            {s.total_cost_monthly > 0 && <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" /> ${s.total_cost_monthly.toLocaleString()}/mo</span>}
                                            {s.duration_seconds > 0 && <span>{s.duration_seconds.toFixed(1)}s</span>}
                                        </div>
                                        {s.error_message && <p className="text-xs text-red-500 mt-1 truncate">{s.error_message}</p>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
