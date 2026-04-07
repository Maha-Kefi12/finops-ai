import { useEffect, useRef } from 'react'
import { Activity, ChevronDown } from 'lucide-react'

const PARTICLES = Array.from({ length: 15 }, (_, i) => ({
    id: i,
    size: Math.random() * 3 + 1,
    left: Math.random() * 100,
    top: Math.random() * 100,
    duration: Math.random() * 20 + 10,
    delay: Math.random() * 10,
    color: ['#6366f1', '#8b5cf6', '#f59e0b', '#10b981', '#3b82f6', '#ec4899'][i % 6],
}))

// Floating connection line SVG for workflow motion
function WorkflowLines() {
    return (
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-[0.07]" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity="0" />
                    <stop offset="50%" stopColor="#6366f1" stopOpacity="1" />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
                </linearGradient>
            </defs>
            {/* Simulated graph edges */}
            <line x1="10%" y1="30%" x2="35%" y2="50%" stroke="url(#lineGrad)" strokeWidth="1.5" />
            <line x1="35%" y1="50%" x2="60%" y2="25%" stroke="url(#lineGrad)" strokeWidth="1.5" />
            <line x1="60%" y1="25%" x2="85%" y2="55%" stroke="url(#lineGrad)" strokeWidth="1.5" />
            <line x1="35%" y1="50%" x2="65%" y2="70%" stroke="url(#lineGrad)" strokeWidth="1" />
            <line x1="65%" y1="70%" x2="85%" y2="55%" stroke="url(#lineGrad)" strokeWidth="1" />
            <line x1="10%" y1="30%" x2="20%" y2="70%" stroke="url(#lineGrad)" strokeWidth="1" />
            <line x1="20%" y1="70%" x2="65%" y2="70%" stroke="url(#lineGrad)" strokeWidth="1" />
            {/* Nodes */}
            <circle cx="10%" cy="30%" r="4" fill="#6366f1" opacity="0.4" />
            <circle cx="35%" cy="50%" r="6" fill="#f59e0b" opacity="0.5" />
            <circle cx="60%" cy="25%" r="5" fill="#10b981" opacity="0.4" />
            <circle cx="85%" cy="55%" r="4" fill="#8b5cf6" opacity="0.4" />
            <circle cx="65%" cy="70%" r="5" fill="#3b82f6" opacity="0.4" />
            <circle cx="20%" cy="70%" r="3.5" fill="#ec4899" opacity="0.3" />
        </svg>
    )
}

export default function HeroSection() {
    return (
        <section className="hero-bg relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
            {/* Floating particles */}
            {PARTICLES.map((p) => (
                <div
                    key={p.id}
                    className="particle"
                    style={{
                        width: p.size,
                        height: p.size,
                        left: `${p.left}%`,
                        top: `${p.top}%`,
                        background: p.color,
                        animationDuration: `${p.duration}s`,
                        animationDelay: `${p.delay}s`,
                        opacity: 0.3,
                    }}
                />
            ))}

            {/* Graph workflow lines */}
            <WorkflowLines />

            {/* Content */}
            <div className="relative z-10 text-center max-w-4xl px-6">
                {/* Logo badge */}
                <div className="animate-fade-in-up animate-stagger-1 inline-flex items-center gap-2 bg-indigo-900/30 border border-indigo-500/30 px-4 py-2 rounded-full mb-8">
                    <div className="w-6 h-6 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
                        <Activity className="w-3.5 h-3.5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-indigo-300">Powered by Graph Intelligence</span>
                </div>

                {/* Title */}
                <h1 className="animate-fade-in-up animate-stagger-2 text-5xl md:text-7xl font-black tracking-tight leading-tight">
                    <span className="text-white">Fin</span>
                    <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-amber-400 bg-clip-text text-transparent">Ops</span>
                    <span className="text-white"> AI</span>
                    <br />
                    <span className="text-3xl md:text-4xl font-bold text-gray-400 mt-2 block">
                        Cloud Architecture Intelligence
                    </span>
                </h1>

                {/* Subtitle */}
                <p className="animate-fade-in-up animate-stagger-3 text-lg text-gray-400 mt-6 max-w-2xl mx-auto leading-relaxed">
                    Ingest your <span className="text-amber-400 font-medium">AWS</span> architecture data,
                    build <span className="text-indigo-400 font-medium">dependency graphs</span>,
                    and discover <span className="text-emerald-400 font-medium">cost hotspots</span> &
                    <span className="text-purple-400 font-medium"> critical bottlenecks</span> using graph theory metrics.
                </p>

                {/* CTA */}
                <div className="animate-fade-in-up animate-stagger-4 mt-10 flex items-center justify-center gap-4">
                    <a href="#ingest" className="btn-primary text-lg px-8 py-3">
                        Get Started
                        <ChevronDown className="w-5 h-5 animate-bounce" />
                    </a>
                </div>

                {/* AWS + Graph Theory keywords */}
                <div className="animate-fade-in-up animate-stagger-4 mt-12 flex flex-wrap items-center justify-center gap-3">
                    {['EC2', 'RDS', 'S3', 'Lambda', 'SQS', 'CloudFront', 'ElastiCache', 'Centrality', 'Betweenness', 'DAG'].map((tag) => (
                        <span key={tag} className="text-xs font-medium text-gray-500 bg-gray-800/50 border border-gray-700/50 px-3 py-1 rounded-full">
                            {tag}
                        </span>
                    ))}
                </div>
            </div>

            {/* Scroll indicator */}
            <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-50">
                <span className="text-xs text-gray-500 uppercase tracking-widest">Scroll</span>
                <div className="w-5 h-8 border border-gray-700 rounded-full flex justify-center pt-1.5">
                    <div className="w-1 h-2 bg-indigo-400 rounded-full animate-bounce" />
                </div>
            </div>
        </section>
    )
}
