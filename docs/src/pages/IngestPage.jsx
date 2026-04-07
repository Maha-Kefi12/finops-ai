import { useEffect, useState, useCallback } from 'react'
import { CheckCircle2, Loader2, Upload, FileJson, AlertCircle, ChevronRight, RefreshCw } from 'lucide-react'
import { getSyntheticFiles, ingestBuiltinFile, ingestUploadedFile } from '../api/client'

const PATTERN_META = {
    ecommerce_medium: { label: 'E-Commerce', desc: 'Product catalog, cart, orders, CDN', color: 'from-indigo-500 to-purple-600' },
    saas_medium: { label: 'SaaS Platform', desc: 'Multi-tenant, reporting, storage', color: 'from-emerald-500 to-teal-600' },
    gaming_large: { label: 'Gaming', desc: 'Game servers, matchmaking, leaderboard', color: 'from-amber-500 to-orange-600' },
    data_pipeline_medium: { label: 'Data Pipeline', desc: 'Ingestion, ETL, analytics', color: 'from-blue-500 to-indigo-600' },
    microservices_large: { label: 'Microservices', desc: '23 services, API gateway, service mesh', color: 'from-pink-500 to-rose-600' },
    serverless_small: { label: 'Serverless', desc: 'Lambda functions, SQS, S3', color: 'from-violet-500 to-purple-600' },
    ml_platform_large: { label: 'ML Platform', desc: 'Training, inference, feature store', color: 'from-orange-500 to-red-600' },
    media_streaming_xlarge: { label: 'Media Streaming', desc: 'Video CDN, transcoding, analytics', color: 'from-teal-500 to-cyan-600' },
}

function FileCard({ file, onIngest, loading, done }) {
    const key = file.filename.replace('.json', '')
    const meta = PATTERN_META[key] || {}
    const sizeKb = (file.size_bytes / 1024).toFixed(1)

    return (
        <div className={`card p-4 flex flex-col gap-3 transition-all ${done ? 'border-emerald-500/40' : 'hover:border-slate-600'}`}>
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${meta.color || 'from-slate-600 to-slate-700'} flex items-center justify-center flex-shrink-0`}>
                        <FileJson className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-slate-200">{meta.label || file.filename}</p>
                        <p className="text-xs text-slate-500">{meta.desc || file.filename}</p>
                    </div>
                </div>
                <span className="text-xs text-slate-600">{sizeKb} KB</span>
            </div>

            <button
                onClick={() => onIngest(file.filename)}
                disabled={loading || done}
                className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${done
                        ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-500/30'
                        : 'bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/20 hover:border-indigo-500/50 disabled:opacity-50 disabled:cursor-not-allowed'
                    }`}
            >
                {loading ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Ingesting...</>
                ) : done ? (
                    <><CheckCircle2 className="w-4 h-4" /> Ingested</>
                ) : (
                    <><ChevronRight className="w-4 h-4" /> Ingest</>
                )}
            </button>
        </div>
    )
}

export default function IngestPage() {
    const [syntheticFiles, setSyntheticFiles] = useState([])
    const [loadingFiles, setLoadingFiles] = useState({})
    const [doneFiles, setDoneFiles] = useState({})
    const [error, setError] = useState(null)
    const [uploadStatus, setUploadStatus] = useState(null)
    const [dragging, setDragging] = useState(false)

    useEffect(() => {
        getSyntheticFiles().then((r) => setSyntheticFiles(r.data.files || [])).catch(() => { })
    }, [])

    const ingestFile = async (filename) => {
        setError(null)
        setLoadingFiles((p) => ({ ...p, [filename]: true }))
        try {
            await ingestBuiltinFile(filename)
            setDoneFiles((p) => ({ ...p, [filename]: true }))
        } catch (e) {
            setError(`Failed to ingest ${filename}: ${e.response?.data?.detail || e.message}`)
        } finally {
            setLoadingFiles((p) => ({ ...p, [filename]: false }))
        }
    }

    const handleUpload = async (file) => {
        if (!file) return
        setUploadStatus('loading')
        try {
            const res = await ingestUploadedFile(file)
            setUploadStatus({ ok: true, name: res.data.name })
        } catch (e) {
            setUploadStatus({ ok: false, msg: e.response?.data?.detail || e.message })
        }
    }

    const onDrop = useCallback((e) => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) handleUpload(file)
    }, [])

    const ingestAll = async () => {
        for (const f of syntheticFiles) {
            if (!doneFiles[f.filename]) {
                await ingestFile(f.filename)
            }
        }
    }

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">Ingest Architecture Data</h1>
                    <p className="text-slate-400 text-sm mt-1">Load synthetic JSON architectures into the graph engine</p>
                </div>
                <button
                    onClick={ingestAll}
                    className="btn-primary"
                >
                    <RefreshCw className="w-4 h-4" /> Ingest All
                </button>
            </div>

            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                </div>
            )}

            {/* Built-in files */}
            <div>
                <h2 className="text-base font-semibold text-slate-300 mb-3">
                    Built-in Synthetic Datasets
                    <span className="ml-2 text-xs font-normal text-slate-500">({syntheticFiles.length} files available)</span>
                </h2>
                <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
                    {syntheticFiles.map((f) => (
                        <FileCard
                            key={f.filename}
                            file={f}
                            onIngest={ingestFile}
                            loading={!!loadingFiles[f.filename]}
                            done={!!doneFiles[f.filename]}
                        />
                    ))}
                    {syntheticFiles.length === 0 && (
                        <div className="col-span-4 card p-8 flex flex-col items-center gap-3 text-slate-600">
                            <FileJson className="w-10 h-10" />
                            <p className="text-sm">No synthetic files found. Make sure the data/synthetic directory is mounted.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Upload area */}
            <div>
                <h2 className="text-base font-semibold text-slate-300 mb-3">Upload Custom JSON</h2>
                <div
                    onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    className={`relative card flex flex-col items-center justify-center gap-4 p-10 text-center cursor-pointer transition-all border-2 border-dashed
            ${dragging ? 'border-indigo-500 bg-indigo-900/10' : 'border-slate-700 hover:border-slate-500'}`}
                    onClick={() => document.getElementById('file-input').click()}
                >
                    <input
                        id="file-input"
                        type="file"
                        accept=".json"
                        className="hidden"
                        onChange={(e) => handleUpload(e.target.files?.[0])}
                    />
                    {uploadStatus === 'loading' ? (
                        <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
                    ) : (
                        <Upload className={`w-10 h-10 ${dragging ? 'text-indigo-400' : 'text-slate-600'}`} />
                    )}
                    <div>
                        <p className="text-sm font-medium text-slate-300">
                            {dragging ? 'Drop to upload' : 'Drag & drop a JSON file or click to browse'}
                        </p>
                        <p className="text-xs text-slate-600 mt-1">Must follow the architecture schema (metadata + services + dependencies)</p>
                    </div>

                    {uploadStatus && uploadStatus !== 'loading' && (
                        <div className={`flex items-center gap-2 text-sm ${uploadStatus.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                            {uploadStatus.ok ? (
                                <><CheckCircle2 className="w-4 h-4" /> Ingested: {uploadStatus.name}</>
                            ) : (
                                <><AlertCircle className="w-4 h-4" /> {uploadStatus.msg}</>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
