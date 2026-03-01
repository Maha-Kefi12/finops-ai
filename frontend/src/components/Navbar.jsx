import { NavLink } from 'react-router-dom'
import { LayoutDashboard, GitBranch, BrainCircuit } from 'lucide-react'

const links = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/graph', label: 'Graph Engine', icon: GitBranch },
    { to: '/analysis', label: 'AI Analysis', icon: BrainCircuit },
]

export default function Navbar() {
    return (
        <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-200 shadow-sm">
            <div className="max-w-7xl mx-auto px-6 flex items-center justify-between h-14">
                {/* Logo — AWS-style */}
                <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center shadow-sm">
                        <span className="text-white font-black text-sm">F</span>
                    </div>
                    <div>
                        <span className="text-sm font-bold text-gray-900 tracking-tight">FinOps AI</span>
                        <span className="text-[10px] text-gray-400 ml-1.5 font-medium">platform</span>
                    </div>
                </div>

                {/* Nav Links */}
                <div className="flex items-center gap-1">
                    {links.map(({ to, label, icon: Icon }) => (
                        <NavLink
                            key={to}
                            to={to}
                            className={({ isActive }) =>
                                `flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 ` +
                                (isActive
                                    ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50')
                            }
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </NavLink>
                    ))}
                </div>

                {/* Status */}
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs text-emerald-700 font-medium">GraphRAG Active</span>
                </div>
            </div>
        </nav>
    )
}
