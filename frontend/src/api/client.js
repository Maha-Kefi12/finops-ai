import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    timeout: 300000,
})

export const getSyntheticFiles = () => api.get('/synthetic-files')
export const ingestBuiltinFile = (filename) => api.post(`/ingest/file/${filename}`)
export const ingestUploadedFile = (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/ingest/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
    })
}
export const ingestFromAws = (region = 'us-east-1', accountId = null) =>
    api.post('/ingest/aws', { region, account_id: accountId }, { timeout: 30000 })
export const getAwsPipelineStatus = (snapshotId) =>
    api.get(`/ingest/aws/status/${snapshotId}`)
export const listSnapshots = () => api.get('/ingest/snapshots')
export const getSnapshot = (id) => api.get(`/ingest/snapshots/${id}`)
export const getGraphMetrics = (archId) => api.get(`/graph-metrics/${archId}`)
export const listGraphs = () => api.get('/graphs')
export const getGraph = (id) => api.get(`/graphs/${id}`)
export const deleteGraph = (id) => api.delete(`/graphs/${id}`)
export const health = () => axios.get('/health')

// ── Analysis Pipeline ────────────────────────────────────────────────
export const listArchitectures = () => api.get('/analyze/architectures')
export const analyzeArchitecture = (filename, architectureId) => {
    const body = {}
    if (filename) body.architecture_file = filename
    if (architectureId) body.architecture_id = architectureId
    return api.post('/analyze', body, { timeout: 300000 })
}
export const listAnalysisResults = () => api.get('/analyze/results')
export const getAnalysisResult = (id) => api.get(`/analyze/results/${id}`)

// ── Topology ─────────────────────────────────────────────────────────
export const analyzeTopology = (filename) =>
    api.post('/topology/analyze', { architecture_file: filename }, { timeout: 300000 })
export const analyzeTopologyById = (architectureId) =>
    api.post('/topology/analyze', { architecture_id: architectureId }, { timeout: 300000 })

// ── LLM Status ──────────────────────────────────────────────────────
export const getLlmStatus = () => axios.get('/api/llm-status')

// ── GraphRAG Traversal ──────────────────────────────────────────────
export const getGraphRAGStrategies = () => api.get('/graphrag/strategies')
export const runEgoNetwork = (archId, seedNode, hops = 2, maxNodes = 50, typeFilter = null) =>
    api.post('/graphrag/ego-network', {
        arch_id: archId, seed_node: seedNode, hops, max_nodes: maxNodes,
        type_filter: typeFilter,
    })
export const runPathBased = (archId, source, target, maxPaths = 5, includeNeighborhood = true) =>
    api.post('/graphrag/path-based', {
        arch_id: archId, source, target, max_paths: maxPaths,
        include_neighborhood: includeNeighborhood,
    })
export const runClusterBased = (archId, minClusterSize = 2, resolution = 1.0, focusNode = null) =>
    api.post('/graphrag/cluster-based', {
        arch_id: archId, min_cluster_size: minClusterSize, resolution,
        focus_node: focusNode,
    })
export const runTemporal = (archId, windowHours = 24, referenceTime = null, sortBy = 'newest') =>
    api.post('/graphrag/temporal', {
        arch_id: archId, window_hours: windowHours, reference_time: referenceTime,
        sort_by: sortBy,
    })
export const runCombinedTraversal = (archId, seedNode = null, targetNode = null, hops = 2, windowHours = 24, strategies = null) =>
    api.post('/graphrag/combined', {
        arch_id: archId, seed_node: seedNode, target_node: targetNode,
        hops, window_hours: windowHours, strategies,
    })

export default api
