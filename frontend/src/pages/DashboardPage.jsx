import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listArchitectures, getLlmStatus } from '../api/client'
import {
    Server, DollarSign, GitBranch, ArrowRight,
    Zap, Shield, Activity, TrendingUp, Layers, Cpu, Database,
    BrainCircuit, CheckCircle2, XCircle, Wifi, WifiOff
} from 'lucide-react'

const PATTERN_STYLES = {
    microservices: { color: '#2563eb', bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', icon: Layers },
    ecommerce: { color: '#d97706', bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', icon: DollarSign },
    saas: { color: '#7c3aed', bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', icon: Cpu },
    gaming: { color: '#e11d48', bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200', icon: Zap },
    data_pipeline: { color: '#059669', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', icon: Activity },
    ml_platform: { color: '#4f46e5', bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200', icon: TrendingUp },
    serverless: { color: '#ca8a04', bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200', icon: Shield },
    media_streaming: { color: '#db2777', bg: 'bg-pink-50', text: 'text-pink-700', border: 'border-pink-200', icon: Server },
}

export default function DashboardPage() {
    const [architectures, setArchitectures] = useState([])
    const [loading, setLoading] = useState(true)
    const [llmStatus, setLlmStatus] = useState(null)
    const navigate = useNavigate()

    useEffect(() => {
        listArchitectures()
            .then(res => setArchitectures(res.data.architectures))
            .catch(() => { })
            .finally(() => setLoading(false))

        getLlmStatus()
            .then(res => setLlmStatus(res.data))
            .catch(() => setLlmStatus({ connected: false, error: 'Cannot reach backend' }))
    }, [])

    const totalServices = architectures.reduce((s, a) => s + a.services, 0)
    const totalCost = architectures.reduce((s, a) => s + a.cost, 0)

    return (
        <div className="max-w-7xl mx-auto px-6 py-10">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-3xl font-bold text-gray-900">
                    AWS Architecture Intelligence
                </h1>
                <p className="mt-2 text-base text-gray-500 max-w-2xl leading-relaxed">
                    Predict cost spikes <strong className="text-blue-600">before they appear</strong> on your AWS bill.
                    Powered by Monte Carlo simulations + GraphRAG-grounded 5-agent AI pipeline.
                </p>
            </div>

            {/* LLM Status Card */}
            {llmStatus && (
                <div className={`mb-6 card overflow-hidden ${llmStatus.connected && llmStatus.model_name ? 'border-emerald-200' : 'border-red-200'}`}>
                    <div className={`h-1 ${llmStatus.connected && llmStatus.model_name ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <div className="p-5 flex items-center gap-5">
                        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${llmStatus.connected && llmStatus.model_name ? 'bg-emerald-50' : 'bg-red-50'}`}>
                            <BrainCircuit className={`w-6 h-6 ${llmStatus.connected && llmStatus.model_name ? 'text-emerald-600' : 'text-red-500'}`} />
                        </div>
                        <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                                {llmStatus.connected && llmStatus.model_name ? (
                                    <>
                                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                        <span className="text-sm font-bold text-emerald-700">LLM Connected</span>
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="w-4 h-4 text-red-500" />
                                        <span className="text-sm font-bold text-red-600">LLM Disconnected</span>
                                    </>
                                )}
                            </div>
                            {llmStatus.connected && llmStatus.model_name ? (
                                <p className="text-xs text-gray-500">
                                    <span className="font-semibold text-gray-700">{llmStatus.model_name}</span>
                                    {' '}• base: <span className="font-mono text-blue-600">{llmStatus.base_model}</span>
                                    {' '}• {llmStatus.parameters} params
                                    {' '}• {llmStatus.size_gb} GB
                                    {' '}• {llmStatus.quantization}
                                </p>
                            ) : (
                                <p className="text-xs text-red-500">{llmStatus.error}</p>
                            )}
                        </div>
                        <div className={`px-3 py-1.5 rounded-full text-xs font-semibold ${llmStatus.connected && llmStatus.model_name ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-600 border border-red-200'}`}>
                            {llmStatus.connected && llmStatus.model_name ? (
                                <span className="flex items-center gap-1.5"><Wifi className="w-3 h-3" /> Online</span>
                            ) : (
                                <span className="flex items-center gap-1.5"><WifiOff className="w-3 h-3" /> Offline</span>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Stats Row */}
            <div className="grid grid-cols-4 gap-4 mb-10">
                {[
                    { label: 'Architectures', value: architectures.length, icon: GitBranch, color: 'blue' },
                    { label: 'AWS Services', value: totalServices, icon: Server, color: 'indigo' },
                    { label: 'Monthly Cost', value: `$${(totalCost / 1000).toFixed(0)}K`, icon: DollarSign, color: 'amber' },
                    { label: 'Simulations', value: '52K', icon: Activity, color: 'emerald' },
                ].map(({ label, value, icon: Icon, color }) => (
                    <div key={label} className="card p-5">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-lg bg-${color}-50 flex items-center justify-center`}>
                                <Icon className={`w-5 h-5 text-${color}-600`} />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-gray-900">{value}</p>
                                <p className="text-xs text-gray-400 uppercase tracking-wider font-medium">{label}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Architecture Cards */}
            <div className="mb-6 flex items-center justify-between">
                <h2 className="text-lg font-bold text-gray-900">Select Architecture to Analyze</h2>
                <p className="text-sm text-gray-400">Click any architecture to run the AI pipeline</p>
            </div>

            {loading ? (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {[...Array(8)].map((_, i) => (
                        <div key={i} className="card h-44 animate-pulse bg-gray-100" />
                    ))}
                </div>
            ) : (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {architectures.map((arch) => {
                        const style = PATTERN_STYLES[arch.pattern] || PATTERN_STYLES.microservices
                        const Icon = style.icon
                        return (
                            <button
                                key={arch.filename}
                                onClick={() => navigate('/analysis', { state: { arch } })}
                                className="group relative card p-5 text-left transition-all duration-200 hover:border-blue-300 hover:shadow-md hover:-translate-y-0.5"
                            >
                                {/* Top color bar */}
                                <div className="absolute top-0 left-0 right-0 h-1 rounded-t-xl opacity-80" style={{ backgroundColor: style.color }} />

                                <div className={`w-10 h-10 rounded-lg ${style.bg} flex items-center justify-center mb-3`}>
                                    <Icon className={`w-5 h-5 ${style.text}`} />
                                </div>

                                <h3 className="font-semibold text-gray-900 text-sm mb-0.5 group-hover:text-blue-600 transition-colors">
                                    {arch.name}
                                </h3>
                                <p className={`text-xs ${style.text} font-medium mb-3 capitalize`}>
                                    {arch.pattern.replace('_', ' ')} • {arch.complexity}
                                </p>

                                <div className="flex items-center justify-between text-xs text-gray-400">
                                    <div className="flex gap-3">
                                        <span><Server className="w-3 h-3 inline mr-0.5" />{arch.services} svcs</span>
                                        <span><DollarSign className="w-3 h-3 inline mr-0.5" />{arch.cost >= 1000 ? `${(arch.cost / 1000).toFixed(0)}K` : arch.cost}/mo</span>
                                    </div>
                                    <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-blue-500 group-hover:translate-x-0.5 transition-all" />
                                </div>
                            </button>
                        )
                    })}
                </div>
            )}

            {/* How It Works */}
            <div className="mt-12 card p-8">
                <h3 className="text-base font-bold text-gray-900 mb-6">How the 5-Agent AWS Analysis Pipeline Works</h3>
                <div className="grid grid-cols-5 gap-4">
                    {[
                        { num: 1, title: 'Infrastructure Topology', desc: 'Analyzes ALB, EC2, RDS dependencies — finds single points of failure', color: 'blue' },
                        { num: 2, title: 'Behavior Analysis', desc: 'Monte Carlo simulations — predicts how costs spike under traffic pressure', color: 'indigo' },
                        { num: 3, title: 'Cost Economics', desc: 'AWS billing analysis — identifies which resources amplify your bill', color: 'amber' },
                        { num: 4, title: 'Root Cause Detective', desc: 'Cross-correlates all data — finds the hidden trigger behind cost spikes', color: 'rose' },
                        { num: 5, title: 'Executive Summary', desc: 'CTO-level verdict — dollar exposure, prioritized AWS actions', color: 'emerald' },
                    ].map(({ num, title, desc, color }, i) => (
                        <div key={num} className="relative">
                            <div className="flex items-center gap-2 mb-3">
                                <div className={`w-7 h-7 rounded-lg bg-${color}-50 flex items-center justify-center text-${color}-600 text-xs font-bold border border-${color}-200`}>
                                    {num}
                                </div>
                                {i < 4 && <div className="flex-1 h-px bg-gray-200" />}
                            </div>
                            <h4 className={`text-xs font-bold text-${color}-600 mb-1`}>{title}</h4>
                            <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
