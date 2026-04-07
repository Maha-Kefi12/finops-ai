import { useEffect, useState, useCallback } from 'react'
import { FileJson, Upload, Loader2, CheckCircle2, AlertCircle, ChevronRight, Zap, Server, DollarSign } from 'lucide-react'
import { getSyntheticFiles, ingestBuiltinFile, ingestUploadedFile, getGraph } from '../api/client'

const PATTERN_THEMES = {
    ecommerce: { gradient: 'from-indigo-500 to-purple-600', icon: '🛒' },
    saas: { gradient: 'from-emerald-500 to-teal-600', icon: '☁️' },
    gaming: { gradient: 'from-amber-500 to-orange-600', icon: '🎮' },
    data_pipeline: { gradient: 'from-blue-500 to-indigo-600', icon: '🔄' },
    microservices: { gradient: 'from-pink-500 to-rose-600', icon: '🔗' },
    serverless: { gradient: 'from-violet-500 to-purple-600', icon: '⚡' },
    ml_platform: { gradient: 'from-orange-500 to-red-600', icon: '🧠' },
    media_streaming: { gradient: 'from-teal-500 to-cyan-600', icon: '🎬' },
}

const formatCost = (v) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)

export default function IngestSection({ onGraphReady }) {
    const [syntheticFiles, setSyntheticFiles] = useState([])
    const [loadingFile, setLoadingFile] = useState(null)
    const [doneFiles, setDoneFiles] = useState({})
    const [error, setError] = useState(null)
    const [dragging, setDragging] = useState(false)
    const [uploadStatus, setUploadStatus] = useState(null)

    useEffect(() => {
        getSyntheticFiles().then((r) => setSyntheticFiles(r.data.files || [])).catch(() => { })
    }, [])

    const ingestFile = async (filename) => {
        setError(null)
        setLoadingFile(filename)
        try {
            const res = await ingestBuiltinFile(filename)
            setDoneFiles((p) => ({ ...p, [filename]: res.data }))
            // Load the graph data
            const graphRes = await getGraph(res.data.id)
            onGraphReady(graphRes.data, res.data)
            // Scroll to graph
            setTimeout(() => document.getElementById('graph')?.scrollIntoView({ behavior: 'smooth' }), 300)
        } catch (e) {
            setError(`Failed to ingest ${filename}: ${e.response?.data?.detail || e.message}`)
        } finally {
            setLoadingFile(null)
        }
    }

    const handleUpload = async (file) => {
        if (!file) return
        setError(null)
        setUploadStatus('loading')
        try {
            const res = await ingestUploadedFile(file)
            setUploadStatus({ ok: true, data: res.data })
            const graphRes = await getGraph(res.data.id)
            onGraphReady(graphRes.data, res.data)
            setTimeout(() => document.getElementById('graph')?.scrollIntoView({ behavior: 'smooth' }), 300)
        } catch (e) {
            setUploadStatus({ ok: false, msg: e.response?.data?.detail || e.message })
            setError(e.response?.data?.detail || e.message)
        }
    }

    const onDrop = useCallback((e) => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) handleUpload(file)
    }, [])

    return (
        <section id="ingest" className="relative py-24 px-6">
            {/* Subtle top gradient fade */}
            <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-transparent to-gray-950" />

            <div className="max-w-6xl mx-auto">
                {/* Section Header */}
                <div className="text-center mb-12">
                    <div className="inline-flex items-center gap-2 bg-amber-900/20 border border-amber-500/25 px-3 py-1.5 rounded-full mb-4">
                        <Zap className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-xs font-medium text-amber-300">Data Ingestion</span>
                    </div>
                    <h2 className="section-title">Load Architecture Data</h2>
                    <p className="section-subtitle mx-auto">
                        Choose a built-in synthetic AWS architecture or upload your own JSON file.
                        Click any card to ingest it and render the dependency graph below.
                    </p>
                </div>

                {error && (
                    <div className="flex items-center gap-2 p-4 bg-red-900/20 border border-red-500/30 rounded-xl text-red-400 text-sm mb-6 max-w-3xl mx-auto">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        {error}
                    </div>
                )}

                {/* Synthetic files grid */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                    {syntheticFiles.map((f) => {
                        const key = f.pattern || f.filename.replace('.json', '').split('_')[0]
                        const theme = PATTERN_THEMES[key] || { gradient: 'from-gray-600 to-gray-700', icon: '📄' }
                        const isLoading = loadingFile === f.filename
                        const isDone = !!doneFiles[f.filename]

                        return (
                            <div
                                key={f.filename}
                                onClick={() => !isLoading && !isDone && ingestFile(f.filename)}
                                className={`card-hover p-5 cursor-pointer group ${isDone ? 'border-emerald-500/40 bg-emerald-900/10' : ''}`}
                            >
                                {/* Header */}
                                <div className="flex items-start justify-between mb-3">
                                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${theme.gradient} flex items-center justify-center text-lg shadow-lg`}>
                                        {theme.icon}
                                    </div>
                                    {isDone && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
                                </div>

                                {/* Title */}
                                <h3 className="text-sm font-bold text-white mb-1">{f.name || f.filename}</h3>
                                <p className="text-xs text-gray-500 mb-3">{f.pattern || 'unknown'} · {f.complexity || 'medium'}</p>

                                {/* Stats */}
                                <div className="flex items-center gap-3 mb-3">
                                    <div className="flex items-center gap-1 text-xs text-gray-400">
                                        <Server className="w-3 h-3" />
                                        {f.total_services || '—'}
                                    </div>
                                    <div className="flex items-center gap-1 text-xs text-amber-400">
                                        <DollarSign className="w-3 h-3" />
                                        {f.total_cost_monthly ? formatCost(f.total_cost_monthly) : '—'}
                                    </div>
                                </div>

                                {/* Action button */}
                                <div className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all ${isDone
                                        ? 'bg-emerald-900/30 text-emerald-400'
                                        : 'bg-indigo-900/20 text-indigo-300 group-hover:bg-indigo-900/40'
                                    }`}>
                                    {isLoading ? (
                                        <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Ingesting...</>
                                    ) : isDone ? (
                                        <><CheckCircle2 className="w-3.5 h-3.5" /> Loaded</>
                                    ) : (
                                        <><ChevronRight className="w-3.5 h-3.5" /> Click to Ingest</>
                                    )}
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* Upload area */}
                <div className="max-w-2xl mx-auto">
                    <div
                        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                        onDragLeave={() => setDragging(false)}
                        onDrop={onDrop}
                        onClick={() => document.getElementById('file-upload').click()}
                        className={`card-hover p-10 text-center cursor-pointer border-2 border-dashed transition-all ${dragging ? 'border-indigo-500/60 bg-indigo-900/10' : 'border-gray-700/60 hover:border-gray-600'
                            }`}
                    >
                        <input
                            id="file-upload"
                            type="file"
                            accept=".json"
                            className="hidden"
                            onChange={(e) => handleUpload(e.target.files?.[0])}
                        />
                        {uploadStatus === 'loading' ? (
                            <Loader2 className="w-10 h-10 text-indigo-400 animate-spin mx-auto" />
                        ) : (
                            <Upload className={`w-10 h-10 mx-auto ${dragging ? 'text-indigo-400' : 'text-gray-600'}`} />
                        )}
                        <p className="text-sm font-medium text-gray-300 mt-4">
                            {dragging ? 'Drop JSON file here' : 'Drag & drop a custom JSON architecture or click to browse'}
                        </p>
                        <p className="text-xs text-gray-600 mt-1">Schema: metadata + services + dependencies</p>

                        {uploadStatus && uploadStatus !== 'loading' && (
                            <div className={`mt-4 flex items-center justify-center gap-2 text-sm ${uploadStatus.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                                {uploadStatus.ok ? (
                                    <><CheckCircle2 className="w-4 h-4" /> Ingested: {uploadStatus.data?.name}</>
                                ) : (
                                    <><AlertCircle className="w-4 h-4" /> {uploadStatus.msg}</>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </section>
    )
}
