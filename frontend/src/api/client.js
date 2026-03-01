import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    timeout: 120000,
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
export const listGraphs = () => api.get('/graphs')
export const getGraph = (id) => api.get(`/graphs/${id}`)
export const deleteGraph = (id) => api.delete(`/graphs/${id}`)
export const health = () => axios.get('/health')

// ── New: Analysis Pipeline ───────────────────────────────────────────
export const listArchitectures = () => api.get('/analyze/architectures')
export const analyzeArchitecture = (filename) =>
    api.post('/analyze', { architecture_file: filename })

// ── LLM Status ──────────────────────────────────────────────────────
export const getLlmStatus = () => axios.get('/api/llm-status')

export default api
