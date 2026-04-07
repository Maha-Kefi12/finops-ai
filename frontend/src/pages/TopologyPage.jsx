import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'
import { analyzeTopology, analyzeTopologyById, listArchitectures, listGraphs, ingestFromAws, getAwsPipelineStatus } from '../api/client'
import {
    Layers, Server, ChevronDown, Search, BrainCircuit,
    TrendingUp, AlertTriangle, CheckCircle2,
    Zap, GitBranch, ArrowRight,
    Target, Eye, RotateCw, Box, Cloud, Loader2,
    Clock, XCircle, DollarSign, Network, Database
} from 'lucide-react'

/* ── AWS Ingestion stages ────────────────────────────────────────────── */
const AWS_STAGES = [
    { key: 'queued',      label: 'Queued',     icon: Clock,        pct: 5 },
    { key: 'discovery',   label: 'Discovery',  icon: Search,       pct: 30 },
    { key: 'graph_build', label: 'Graph Build', icon: Network,      pct: 55 },
    { key: 'storing',     label: 'Storage',    icon: Database,     pct: 75 },
    { key: 'llm_report',  label: 'LLM Report', icon: BrainCircuit, pct: 90 },
    { key: 'completed',   label: 'Done',       icon: CheckCircle2, pct: 100 },
]

function stagePct(stage) {
    if (stage === 'failed') return 0
    const norm = stage?.replace(/_done$/, '').replace(/^stored$/, 'storing').replace(/^llm_done$/, 'llm_report') || 'queued'
    return AWS_STAGES.find(s => s.key === norm)?.pct || 10
}

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
                        {isDone ? 'AWS Ingestion Complete — Generating Topology...' : isFailed ? 'Ingestion Failed' : 'AWS Live Discovery'}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    {elapsed > 0 && (
                        <span className="text-xs text-gray-500 font-mono bg-white px-2 py-1 rounded border border-gray-200">
                            {elapsed.toFixed(1)}s
                        </span>
                    )}
                    {!isDone && !isFailed && onCancel && (
                        <button onClick={onCancel} className="text-xs text-gray-400 hover:text-gray-600">Cancel</button>
                    )}
                </div>
            </div>
            <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden mb-2">
                <div className={`h-full rounded-full transition-all duration-700 ease-out ${
                    isDone ? 'bg-emerald-500' : isFailed ? 'bg-red-500' : 'bg-gradient-to-r from-amber-400 to-orange-500'
                }`} style={{ width: `${pct}%` }} />
            </div>
            <div className="flex items-center justify-between mb-2">
                {AWS_STAGES.map((s) => {
                    const Icon = s.icon
                    const currentPct = stagePct(stage)
                    const isActive = !isFailed && Math.abs(currentPct - s.pct) < 15 && currentPct <= s.pct
                    const isComplete = !isFailed && currentPct > s.pct
                    return (
                        <div key={s.key} className="flex flex-col items-center gap-1">
                            <div className={`w-7 h-7 rounded-full flex items-center justify-center transition-all duration-300 ${
                                isComplete ? 'bg-emerald-100 text-emerald-600 border border-emerald-300'
                                : isActive ? 'bg-amber-100 text-amber-700 border border-amber-400 ring-2 ring-amber-200'
                                : 'bg-gray-100 text-gray-400 border border-gray-200'
                            }`}>
                                {isComplete ? <CheckCircle2 className="w-3.5 h-3.5" />
                                 : isActive ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                 : <Icon className="w-3.5 h-3.5" />}
                            </div>
                            <span className={`text-[9px] font-medium ${isActive ? 'text-amber-700' : isComplete ? 'text-emerald-600' : 'text-gray-400'}`}>
                                {s.label}
                            </span>
                        </div>
                    )
                })}
            </div>
            {detail && (
                <div className={`rounded-lg px-3 py-2 text-xs flex items-center gap-2 ${
                    isFailed ? 'bg-red-50 text-red-700 border border-red-200'
                    : isDone ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-white text-gray-600 border border-gray-200'
                }`}>
                    {!isDone && !isFailed && <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />}
                    {detail}
                </div>
            )}
            {isDone && totalServices > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-3">
                    <div className="bg-white rounded-lg p-2.5 border border-emerald-200 shadow-sm">
                        <p className="text-xs text-gray-500 flex items-center gap-1"><Server className="w-3 h-3" /> Resources</p>
                        <p className="text-base font-bold text-gray-900">{totalServices}</p>
                    </div>
                    <div className="bg-white rounded-lg p-2.5 border border-emerald-200 shadow-sm">
                        <p className="text-xs text-gray-500 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Monthly Cost</p>
                        <p className="text-base font-bold text-gray-900">${(totalCost || 0).toLocaleString()}</p>
                    </div>
                </div>
            )}
            {isFailed && error && (
                <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3">
                    <p className="text-xs text-red-600 font-mono break-all">{error}</p>
                    <p className="text-xs text-gray-500 mt-1">Check AWS credentials in .env</p>
                </div>
            )}
        </div>
    )
}

const RISK_COLORS = {
    critical: { bg: '#fef2f2', border: '#fecaca', text: '#991b1b' },
    high: { bg: '#fffbeb', border: '#fde68a', text: '#92400e' },
    moderate: { bg: '#eff6ff', border: '#bfdbfe', text: '#1e40af' },
    low: { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534' },
}

/* ── Three.js 3D Canvas ─────────────────────────────────────────────── */
function Topology3DCanvas({ nodes, edges, tiers, onNodeHover }) {
    const mountRef = useRef()
    const sceneRef = useRef()
    const rendererRef = useRef()
    const cameraRef = useRef()
    const controlsRef = useRef()
    const animRef = useRef()
    const nodeMapRef = useRef({})
    const tooltipRef = useRef()
    const raycasterRef = useRef(new THREE.Raycaster())
    const mouseRef = useRef(new THREE.Vector2())
    const hoveredRef = useRef(null)

    useEffect(() => {
        if (!mountRef.current || !nodes || nodes.length === 0) return
        const mount = mountRef.current
        const W = mount.clientWidth
        const H = 650

        // Scene
        const scene = new THREE.Scene()
        scene.background = new THREE.Color(0x0f172a)
        scene.fog = new THREE.Fog(0x0f172a, 400, 900)
        sceneRef.current = scene

        // Camera
        const camera = new THREE.PerspectiveCamera(55, W / H, 1, 2000)
        camera.position.set(0, 120, 350)
        camera.lookAt(0, 0, -100)
        cameraRef.current = camera

        // Renderer
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
        renderer.setSize(W, H)
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        mount.appendChild(renderer.domElement)
        rendererRef.current = renderer

        // Controls
        const controls = new OrbitControls(camera, renderer.domElement)
        controls.enableDamping = true
        controls.dampingFactor = 0.08
        controls.target.set(0, 0, -100)
        controls.maxDistance = 700
        controls.minDistance = 60
        controlsRef.current = controls

        // Lights
        scene.add(new THREE.AmbientLight(0xffffff, 0.6))
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
        dirLight.position.set(100, 200, 100)
        scene.add(dirLight)
        const pointLight = new THREE.PointLight(0x818cf8, 0.5, 600)
        pointLight.position.set(-100, 100, 0)
        scene.add(pointLight)

        // Grid helper (dark subtle grid)
        const gridHelper = new THREE.GridHelper(600, 30, 0x1e293b, 0x1e293b)
        gridHelper.position.y = -30
        scene.add(gridHelper)

        // Tier planes (semi-transparent layers)
        if (tiers && tiers.length > 0) {
            tiers.forEach(tier => {
                const z = tier.z_position ?? 0
                const planeGeo = new THREE.PlaneGeometry(500, 60)
                const planeMat = new THREE.MeshBasicMaterial({
                    color: 0x334155, transparent: true, opacity: 0.12, side: THREE.DoubleSide
                })
                const plane = new THREE.Mesh(planeGeo, planeMat)
                plane.rotation.x = -Math.PI / 2
                plane.position.set(0, -25, z)
                scene.add(plane)

                // Tier label sprite
                const canvas = document.createElement('canvas')
                canvas.width = 512
                canvas.height = 64
                const ctx = canvas.getContext('2d')
                ctx.fillStyle = '#94a3b8'
                ctx.font = 'bold 28px Inter, system-ui, sans-serif'
                ctx.textAlign = 'left'
                ctx.fillText(tier.name || '', 10, 40)
                const tex = new THREE.CanvasTexture(canvas)
                const spriteMat = new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.7 })
                const sprite = new THREE.Sprite(spriteMat)
                sprite.scale.set(120, 15, 1)
                sprite.position.set(-230, -20, z)
                scene.add(sprite)
            })
        }

        // Nodes
        const nodeMap = {}
        const nodeGroup = new THREE.Group()
        nodes.forEach(node => {
            const size = node.size || 8
            const color = node.color || '#3b82f6'

            // Sphere
            const geo = new THREE.SphereGeometry(size * 0.6, 24, 24)
            const mat = new THREE.MeshPhongMaterial({
                color: new THREE.Color(color),
                emissive: new THREE.Color(color),
                emissiveIntensity: 0.3,
                shininess: 60,
            })
            const mesh = new THREE.Mesh(geo, mat)
            const nx = parseFloat(node.x) || 0
            const ny = parseFloat(node.y) || 0
            const nz = parseFloat(node.z) || 0
            mesh.position.set(nx, ny, nz)
            mesh.userData = node
            nodeGroup.add(mesh)

            // Glow ring
            const ringGeo = new THREE.RingGeometry(size * 0.7, size * 0.9, 32)
            const ringMat = new THREE.MeshBasicMaterial({
                color: new THREE.Color(color), transparent: true, opacity: 0.15, side: THREE.DoubleSide
            })
            const ring = new THREE.Mesh(ringGeo, ringMat)
            ring.position.copy(mesh.position)
            ring.lookAt(camera.position)
            nodeGroup.add(ring)

            // Label sprite
            const labelCanvas = document.createElement('canvas')
            labelCanvas.width = 512
            labelCanvas.height = 80
            const labelCtx = labelCanvas.getContext('2d')
            labelCtx.fillStyle = '#e2e8f0'
            labelCtx.font = 'bold 24px Inter, system-ui, sans-serif'
            labelCtx.textAlign = 'center'
            const displayName = (node.name || node.id || '').substring(0, 20)
            labelCtx.fillText(displayName, 256, 30)
            labelCtx.fillStyle = '#64748b'
            labelCtx.font = '18px Inter, system-ui, sans-serif'
            labelCtx.fillText(node.aws_service || node.type || '', 256, 58)
            const labelTex = new THREE.CanvasTexture(labelCanvas)
            const labelSpriteMat = new THREE.SpriteMaterial({ map: labelTex, transparent: true })
            const labelSprite = new THREE.Sprite(labelSpriteMat)
            labelSprite.scale.set(60, 10, 1)
            labelSprite.position.set(nx, ny + size * 0.8 + 8, nz)
            nodeGroup.add(labelSprite)

            nodeMap[node.id] = mesh
        })
        scene.add(nodeGroup)
        nodeMapRef.current = nodeMap

        // Edges
        const edgeGroup = new THREE.Group()
        edges.forEach(edge => {
            const srcMesh = nodeMap[edge.source]
            const tgtMesh = nodeMap[edge.target]
            if (!srcMesh || !tgtMesh) return

            const points = [srcMesh.position.clone(), tgtMesh.position.clone()]
            const geo = new THREE.BufferGeometry().setFromPoints(points)
            const edgeColor = edge.color || '#475569'
            const mat = new THREE.LineBasicMaterial({
                color: new THREE.Color(edgeColor), transparent: true, opacity: 0.5
            })
            const line = new THREE.Line(geo, mat)
            edgeGroup.add(line)

            // Arrow cone
            const dir = new THREE.Vector3().subVectors(tgtMesh.position, srcMesh.position).normalize()
            const dist = srcMesh.position.distanceTo(tgtMesh.position)
            const coneGeo = new THREE.ConeGeometry(2, 6, 8)
            const coneMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(edgeColor), transparent: true, opacity: 0.6 })
            const cone = new THREE.Mesh(coneGeo, coneMat)
            const arrowPos = srcMesh.position.clone().add(dir.clone().multiplyScalar(dist * 0.75))
            cone.position.copy(arrowPos)
            cone.lookAt(tgtMesh.position)
            cone.rotateX(Math.PI / 2)
            edgeGroup.add(cone)
        })
        scene.add(edgeGroup)

        // Handle mousemove for hover
        const onMouseMove = (e) => {
            const rect = renderer.domElement.getBoundingClientRect()
            mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
            mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
        }
        renderer.domElement.addEventListener('mousemove', onMouseMove)

        // Animate
        const clock = new THREE.Clock()
        const animate = () => {
            animRef.current = requestAnimationFrame(animate)
            const t = clock.getElapsedTime()

            // Subtle pulse on nodes
            nodeGroup.children.forEach(child => {
                if (child.isMesh && child.geometry.type === 'SphereGeometry') {
                    const s = 1 + Math.sin(t * 2 + child.position.x * 0.05) * 0.04
                    child.scale.setScalar(s)
                }
            })

            // Raycasting for hover
            raycasterRef.current.setFromCamera(mouseRef.current, camera)
            const spheres = nodeGroup.children.filter(c => c.isMesh && c.geometry.type === 'SphereGeometry')
            const intersects = raycasterRef.current.intersectObjects(spheres)
            if (intersects.length > 0) {
                const hit = intersects[0].object
                if (hoveredRef.current !== hit) {
                    if (hoveredRef.current) {
                        hoveredRef.current.material.emissiveIntensity = 0.3
                    }
                    hoveredRef.current = hit
                    hit.material.emissiveIntensity = 0.8
                    onNodeHover?.(hit.userData)
                }
            } else {
                if (hoveredRef.current) {
                    hoveredRef.current.material.emissiveIntensity = 0.3
                    hoveredRef.current = null
                    onNodeHover?.(null)
                }
            }

            controls.update()
            renderer.render(scene, camera)
        }
        animate()

        // Resize
        const onResize = () => {
            const w = mount.clientWidth
            camera.aspect = w / H
            camera.updateProjectionMatrix()
            renderer.setSize(w, H)
        }
        window.addEventListener('resize', onResize)

        return () => {
            window.removeEventListener('resize', onResize)
            renderer.domElement.removeEventListener('mousemove', onMouseMove)
            cancelAnimationFrame(animRef.current)
            renderer.dispose()
            if (mount.contains(renderer.domElement)) {
                mount.removeChild(renderer.domElement)
            }
        }
    }, [nodes, edges, tiers])

    return <div ref={mountRef} className="w-full rounded-xl overflow-hidden" style={{ height: 650 }} />
}

/* ── Sub-components ──────────────────────────────────────────────────── */
function TierCard({ tier }) {
    return (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <h4 className="text-sm font-bold text-gray-900 mb-1">{tier.name}</h4>
            <p className="text-xs text-gray-500 mb-3">{tier.role}</p>
            <div className="flex flex-wrap gap-1.5">
                {(tier.services || []).map((s, i) => (
                    <span key={i} className="text-[11px] bg-blue-50 text-blue-700 px-2 py-1 rounded-md border border-blue-100 font-medium">
                        {s}
                    </span>
                ))}
            </div>
        </div>
    )
}

function NodeCard({ node }) {
    const risk = RISK_COLORS[node.risk_level] || RISK_COLORS.moderate
    return (
        <div className="rounded-xl border p-4 transition-all hover:shadow-sm"
            style={{ backgroundColor: risk.bg, borderColor: risk.border }}>
            <div className="flex items-start justify-between mb-2">
                <div>
                    <h4 className="text-sm font-bold" style={{ color: risk.text }}>{node.name}</h4>
                    <p className="text-xs text-gray-500">{node.aws_service || node.type}</p>
                </div>
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: risk.border, color: risk.text }}>
                    {node.risk_level}
                </span>
            </div>
            <p className="text-xs text-gray-600 mb-2">{node.role}</p>
            <div className="flex items-center gap-2">
                <span className="text-[10px] bg-white/60 px-2 py-0.5 rounded border border-gray-200 text-gray-500">
                    {node.tier}
                </span>
            </div>
        </div>
    )
}

/* ── Main Page ───────────────────────────────────────────────────────── */
export default function TopologyPage() {
    const [architectures, setArchitectures] = useState([])
    const [dbArchitectures, setDbArchitectures] = useState([])
    const [selectedArch, setSelectedArch] = useState(null)
    const [result, setResult] = useState(null)
    const [loading, setLoading] = useState(false)
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const [activeTab, setActiveTab] = useState('graph')
    const [hoveredNode, setHoveredNode] = useState(null)
    const [awsLoading, setAwsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [awsProgress, setAwsProgress] = useState(null)
    const awsPollRef = useRef(null)
    const awsStartRef = useRef(null)
    const awsTimerRef = useRef(null)

    useEffect(() => {
        listArchitectures()
            .then(res => setArchitectures(res.data.architectures || []))
            .catch(() => {})
        listGraphs()
            .then(res => setDbArchitectures(res.data.architectures || []))
            .catch(() => {})
        return () => {
            if (awsPollRef.current) clearInterval(awsPollRef.current)
            if (awsTimerRef.current) clearInterval(awsTimerRef.current)
        }
    }, [])

    function cancelAwsDiscovery() {
        if (awsPollRef.current) clearInterval(awsPollRef.current)
        if (awsTimerRef.current) clearInterval(awsTimerRef.current)
        awsPollRef.current = null; awsTimerRef.current = null
        setAwsLoading(false); setAwsProgress(null)
    }

    async function handleAwsLiveTopology() {
        setDropdownOpen(false)
        setAwsLoading(true)
        setResult(null)
        setError(null)
        setAwsProgress({ stage: 'queued', detail: 'Starting AWS discovery...', elapsed: 0 })
        awsStartRef.current = Date.now()
        awsTimerRef.current = setInterval(() => {
            setAwsProgress(prev => prev ? { ...prev, elapsed: (Date.now() - awsStartRef.current) / 1000 } : prev)
        }, 500)

        try {
            const res = await ingestFromAws('us-east-1')
            const snapshotId = res.data?.snapshot_id
            if (!snapshotId) throw new Error('No snapshot_id returned from AWS ingestion')

            awsPollRef.current = setInterval(async () => {
                try {
                    // ── Client-side timeout: stop if polling > 5 min ──
                    const elapsedMs = Date.now() - awsStartRef.current
                    if (elapsedMs > 5 * 60 * 1000) {
                        clearInterval(awsPollRef.current); clearInterval(awsTimerRef.current)
                        awsPollRef.current = null; awsTimerRef.current = null
                        setAwsLoading(false)
                        setAwsProgress(prev => ({
                            ...prev,
                            stage: 'failed',
                            detail: 'Discovery timed out after 5 minutes. Please retry.',
                            error: 'Pipeline timed out — please try again.',
                        }))
                        return
                    }

                    const statusRes = await getAwsPipelineStatus(snapshotId)
                    const data = statusRes.data
                    setAwsProgress(prev => ({
                        stage: data.pipeline_stage || 'queued',
                        detail: data.pipeline_detail || '',
                        elapsed: prev?.elapsed || 0,
                        totalServices: data.total_services || 0,
                        totalCost: data.total_cost_monthly || 0,
                        error: data.error_message,
                    }))

                    if (data.status === 'completed' || data.status === 'failed') {
                        clearInterval(awsPollRef.current); clearInterval(awsTimerRef.current)
                        awsPollRef.current = null; awsTimerRef.current = null
                        if (data.duration_seconds > 0) {
                            setAwsProgress(prev => prev ? { ...prev, elapsed: data.duration_seconds } : prev)
                        }

                        if (data.status === 'completed' && data.architecture_id) {
                            const archRes = await listArchitectures()
                            setArchitectures(archRes.data.architectures || [])
                            const graphsRes = await listGraphs()
                            setDbArchitectures(graphsRes.data.architectures || [])
                            const newArch = {
                                architecture_id: data.architecture_id,
                                name: `AWS Live (${data.region || 'us-east-1'})`,
                                source: 'db', pattern: 'discovered',
                                services: data.total_services || 0,
                            }
                            setSelectedArch(newArch)
                            setResult(null)
                            setTimeout(() => setAwsProgress(null), 3000)
                        }
                        setAwsLoading(false)
                    }
                } catch { /* transient poll error */ }
            }, 1500)
        } catch (e) {
            clearInterval(awsTimerRef.current); awsTimerRef.current = null
            setAwsLoading(false)
            setAwsProgress(prev => ({
                ...prev,
                stage: 'failed',
                detail: e.response?.data?.detail || e.message || 'AWS ingestion request failed',
                error: e.response?.data?.detail || e.message,
            }))
        }
    }

    const allArchitectures = useMemo(() => {
        const items = architectures.map(a => ({ ...a, source: 'file' }))
        dbArchitectures.forEach(a => {
            if (!items.find(i => i.name === a.name)) {
                items.push({
                    name: a.name,
                    filename: null,
                    architecture_id: a.id,
                    services: a.total_services,
                    pattern: a.pattern || 'ingested',
                    source: 'db',
                })
            }
        })
        return items
    }, [architectures, dbArchitectures])

    async function runTopology() {
        if (!selectedArch) return
        setLoading(true)
        setResult(null)
        setError(null)
        try {
            let res
            if (selectedArch.source === 'db' && selectedArch.architecture_id) {
                res = await analyzeTopologyById(selectedArch.architecture_id)
            } else {
                res = await analyzeTopology(selectedArch.filename)
            }
            setResult(res.data)
        } catch (e) {
            console.error('Topology analysis failed:', e)
            const msg = e.response?.data?.detail || e.message || 'Topology analysis failed'
            setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        }
        setLoading(false)
    }

    useEffect(() => {
        if (selectedArch) runTopology()
    }, [selectedArch])

    const tabs = [
        { key: 'graph', label: '3D Topology', icon: Box },
        { key: 'overview', label: 'Overview', icon: Eye },
        { key: 'services', label: 'Services', icon: Server },
        { key: 'patterns', label: 'Patterns', icon: Layers },
    ]

    return (
        <div className="max-w-7xl mx-auto px-6 py-10">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                        <Layers className="w-7 h-7 text-indigo-600" />
                        3D Architecture Topology
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        LLM-generated 3D graph layout — every coordinate placed by FinOps-R1
                    </p>
                </div>

                <div className="relative">
                    <button onClick={() => setDropdownOpen(!dropdownOpen)} className="btn-primary">
                        <Search className="w-4 h-4" />
                        {awsLoading ? 'Discovering AWS...' : selectedArch?.name || 'Select Architecture'}
                        {awsLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    {dropdownOpen && (
                        <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-30 max-h-72 overflow-y-auto">
                            {/* AWS Live Option */}
                            <button onClick={handleAwsLiveTopology}
                                className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 transition-colors flex items-center gap-2 mb-1 border border-amber-200">
                                <Cloud className="w-4 h-4 text-amber-600" />
                                <div className="flex-1">
                                    <span className="font-bold">AWS Live Discovery</span>
                                    <p className="text-[10px] text-amber-600">Ingest & visualize real AWS infrastructure</p>
                                </div>
                            </button>
                            <div className="h-px bg-gray-100 my-1" />
                            {allArchitectures.map((a, idx) => (
                                <button key={a.filename || a.architecture_id || idx}
                                    onClick={() => { setSelectedArch(a); setDropdownOpen(false); setResult(null) }}
                                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors">
                                    <div className="flex justify-between items-center">
                                        <span className="font-medium">{a.name}</span>
                                        <span className="text-xs text-gray-400">{a.services} svcs</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-gray-400 capitalize">{a.pattern}</span>
                                        {a.source === 'db' && (
                                            <span className="text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded border border-emerald-200">ingested</span>
                                        )}
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* AWS Ingestion Progress */}
            {awsProgress && <AwsProgressBar progress={awsProgress} onCancel={cancelAwsDiscovery} />}

            {/* Loading */}
            {loading && (
                <div className="card p-16 flex flex-col items-center justify-center mb-8">
                    <div className="relative mb-6">
                        <div className="w-16 h-16 rounded-full border-4 border-indigo-100 border-t-indigo-600 animate-spin" />
                        <Layers className="w-7 h-7 text-indigo-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                    </div>
                    <p className="text-gray-900 font-semibold mb-1">Generating 3D Topology</p>
                    <p className="text-sm text-gray-400 text-center max-w-md">
                        LLM is analyzing services and assigning 3D spatial coordinates, tier groupings, and risk levels
                    </p>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="card p-6 border-l-4 border-l-red-500 bg-red-50/30 mb-6">
                    <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle className="w-5 h-5 text-red-600" />
                        <h3 className="text-sm font-bold text-red-700">Topology Analysis Failed</h3>
                    </div>
                    <p className="text-sm text-red-600">{error}</p>
                    <p className="text-xs text-gray-500 mt-2">Make sure the LLM (Ollama) is running and the model is available.</p>
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="space-y-6 animate-fade-in-up">
                    {/* Summary Banner */}
                    <div className="card overflow-hidden">
                        <div className="h-1.5 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600" />
                        <div className="p-6">
                            <div className="flex items-center gap-2 mb-3">
                                <BrainCircuit className="w-5 h-5 text-indigo-600" />
                                <h2 className="text-lg font-bold text-gray-900">Architecture Overview</h2>
                                {result.architecture_type && (
                                    <span className="text-xs bg-indigo-50 text-indigo-700 px-2.5 py-1 rounded-full border border-indigo-200 font-medium uppercase">
                                        {result.architecture_type}
                                    </span>
                                )}
                            </div>
                            <p className="text-sm text-gray-600 leading-relaxed mb-4">{result.summary}</p>
                            <div className="grid grid-cols-4 gap-3">
                                {[
                                    { label: 'Services', value: result.n_services },
                                    { label: 'Dependencies', value: result.n_dependencies },
                                    { label: 'Monthly Cost', value: `$${(result.total_cost_monthly || 0).toLocaleString()}` },
                                    { label: 'Density', value: (result.density || 0).toFixed(3) },
                                ].map(({ label, value }) => (
                                    <div key={label} className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                                        <p className="text-[10px] text-gray-400 uppercase mb-0.5">{label}</p>
                                        <p className="text-sm font-bold text-gray-900">{value}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex gap-1.5 border-b border-gray-200 pb-0">
                        {tabs.map(({ key, label, icon: Icon }) => (
                            <button key={key} onClick={() => setActiveTab(key)}
                                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 ${activeTab === key
                                    ? 'text-indigo-700 border-indigo-600 bg-indigo-50'
                                    : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
                                    }`}>
                                <Icon className="w-4 h-4" /> {label}
                            </button>
                        ))}
                    </div>

                    {/* 3D Graph Tab */}
                    {activeTab === 'graph' && result.nodes && (
                        <div className="relative">
                            <div className="card overflow-hidden p-0">
                                <Topology3DCanvas
                                    nodes={result.nodes || []}
                                    edges={result.edges || []}
                                    tiers={result.tiers || []}
                                    onNodeHover={setHoveredNode}
                                />
                            </div>
                            {/* Hover tooltip */}
                            {hoveredNode && (
                                <div className="absolute top-4 right-4 w-72 bg-white/95 backdrop-blur-sm border border-gray-200 rounded-xl p-4 shadow-lg z-20">
                                    <div className="flex items-center justify-between mb-2">
                                        <h4 className="text-sm font-bold text-gray-900">{hoveredNode.name}</h4>
                                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                                            style={{
                                                backgroundColor: RISK_COLORS[hoveredNode.risk_level]?.border || '#bfdbfe',
                                                color: RISK_COLORS[hoveredNode.risk_level]?.text || '#1e40af'
                                            }}>
                                            {hoveredNode.risk_level}
                                        </span>
                                    </div>
                                    <p className="text-xs text-gray-500 mb-1">{hoveredNode.aws_service || hoveredNode.type}</p>
                                    <p className="text-xs text-gray-600">{hoveredNode.role}</p>
                                    <div className="mt-2 pt-2 border-t border-gray-100 flex items-center gap-2 text-[10px] text-gray-400">
                                        <span>Tier: {hoveredNode.tier}</span>
                                        <span>x:{hoveredNode.x} y:{hoveredNode.y} z:{hoveredNode.z}</span>
                                    </div>
                                </div>
                            )}
                            {/* Legend */}
                            <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur-sm border border-gray-200 rounded-lg p-3 shadow-sm z-20">
                                <p className="text-[10px] text-gray-400 uppercase font-bold mb-2">Risk Levels</p>
                                <div className="space-y-1">
                                    {[
                                        { label: 'Critical', color: '#ef4444' },
                                        { label: 'High', color: '#f59e0b' },
                                        { label: 'Moderate', color: '#3b82f6' },
                                        { label: 'Low', color: '#22c55e' },
                                    ].map(({ label, color }) => (
                                        <div key={label} className="flex items-center gap-1.5">
                                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                                            <span className="text-[10px] text-gray-500">{label}</span>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-[9px] text-gray-400 mt-2 pt-2 border-t border-gray-200">
                                    Drag to rotate / Scroll to zoom
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Overview Tab */}
                    {activeTab === 'overview' && (
                        <div className="grid grid-cols-2 gap-6">
                            {result.critical_path && result.critical_path.length > 0 && (
                                <div className="card p-5 col-span-2">
                                    <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                                        <Zap className="w-4 h-4 text-amber-500" /> Critical Path
                                    </h3>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        {result.critical_path.map((s, i) => (
                                            <div key={i} className="flex items-center gap-2">
                                                <span className="text-sm bg-amber-50 text-amber-800 px-3 py-1.5 rounded-lg border border-amber-200 font-medium">
                                                    {s}
                                                </span>
                                                {i < result.critical_path.length - 1 && (
                                                    <ArrowRight className="w-4 h-4 text-gray-300" />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {result.tiers && result.tiers.length > 0 && (
                                <div className="col-span-2">
                                    <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                                        <Layers className="w-4 h-4 text-indigo-500" /> Architecture Tiers
                                    </h3>
                                    <div className="grid grid-cols-2 gap-3">
                                        {result.tiers.map((t, i) => <TierCard key={i} tier={t} />)}
                                    </div>
                                </div>
                            )}

                            {result.strengths && result.strengths.length > 0 && (
                                <div className="card p-5">
                                    <h3 className="text-sm font-bold text-emerald-700 mb-3 flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4" /> Strengths
                                    </h3>
                                    <div className="space-y-2">
                                        {result.strengths.map((s, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                                                <p className="text-sm text-gray-700">{s}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {result.weaknesses && result.weaknesses.length > 0 && (
                                <div className="card p-5">
                                    <h3 className="text-sm font-bold text-amber-700 mb-3 flex items-center gap-2">
                                        <AlertTriangle className="w-4 h-4" /> Weaknesses
                                    </h3>
                                    <div className="space-y-2">
                                        {result.weaknesses.map((w, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                                                <p className="text-sm text-gray-700">{w}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {result.recommendations && result.recommendations.length > 0 && (
                                <div className="col-span-2">
                                    <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                                        <TrendingUp className="w-4 h-4 text-blue-500" /> Recommendations
                                    </h3>
                                    <div className="grid grid-cols-2 gap-3">
                                        {result.recommendations.map((s, i) => (
                                            <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
                                                <div className="flex items-start gap-3">
                                                    <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center flex-shrink-0">
                                                        <span className="text-xs font-bold text-blue-600">{i + 1}</span>
                                                    </div>
                                                    <p className="text-sm text-gray-700 leading-relaxed">{s}</p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Services Tab */}
                    {activeTab === 'services' && result.nodes && (
                        <div className="grid grid-cols-3 gap-3">
                            {result.nodes.map((n, i) => (
                                <NodeCard key={i} node={n} />
                            ))}
                        </div>
                    )}

                    {/* Patterns Tab */}
                    {activeTab === 'patterns' && (
                        <div className="space-y-4">
                            {result.edges && result.edges.length > 0 && (
                                <div className="card p-5">
                                    <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                                        <Target className="w-4 h-4 text-purple-500" /> Edge Analysis
                                    </h3>
                                    <div className="space-y-2.5">
                                        {result.edges.filter(e => e.label).slice(0, 20).map((e, i) => (
                                            <div key={i} className="flex items-start gap-2.5 p-3 bg-purple-50 rounded-lg border border-purple-100">
                                                <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-purple-500 flex-shrink-0" />
                                                <p className="text-sm text-gray-700">
                                                    <span className="font-medium">{e.source}</span>
                                                    <ArrowRight className="w-3 h-3 inline mx-1 text-gray-400" />
                                                    <span className="font-medium">{e.target}</span>
                                                    <span className="text-gray-400 ml-2">({e.label})</span>
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {result.cycles > 0 && (
                                <div className="card p-5 border-l-4 border-l-red-500 bg-red-50/30">
                                    <div className="flex items-center gap-2 mb-2">
                                        <AlertTriangle className="w-5 h-5 text-red-600" />
                                        <h3 className="text-sm font-bold text-gray-900">Circular Dependencies</h3>
                                    </div>
                                    <p className="text-sm text-gray-700">
                                        {result.cycles} circular dependency cycle(s) detected.
                                        Circular dependencies can cause retry storms and unpredictable cost amplification.
                                    </p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* LLM Attribution */}
                    <div className="flex items-center gap-1.5 justify-center py-4">
                        <BrainCircuit className="w-3 h-3 text-gray-300" />
                        <span className="text-[10px] text-gray-400">
                            3D layout, node placement, and analysis generated by FinOps-R1 AI -- no force-directed physics
                        </span>
                    </div>
                </div>
            )}

            {/* Empty State */}
            {!loading && !result && !selectedArch && (
                <div className="card p-20 text-center">
                    <Box className="w-16 h-16 text-gray-200 mx-auto mb-4" />
                    <h3 className="text-lg font-bold text-gray-400 mb-2">Select an Architecture</h3>
                    <p className="text-sm text-gray-400 max-w-md mx-auto leading-relaxed">
                        Choose an architecture from the dropdown above.
                        The FinOps-R1 LLM will generate a full 3D topology with spatial coordinates, tier groupings, and risk analysis.
                    </p>
                </div>
            )}
        </div>
    )
}
