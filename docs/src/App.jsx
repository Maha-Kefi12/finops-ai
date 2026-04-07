import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import DashboardPage from './pages/DashboardPage'
import GraphEnginePage from './pages/GraphEnginePage'
import PipelinePage from './pages/PipelinePage'
import AnalysisPage from './pages/AnalysisPage'
import TopologyPage from './pages/TopologyPage'
import MetricsPage from './pages/MetricsPage'
import GraphRAGPage from './pages/GraphRAGPage'

export default function App() {
    return (
        <Router>
            <div className="min-h-screen bg-gray-50">
                <Navbar />
                <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/pipeline" element={<PipelinePage />} />
                    <Route path="/graph" element={<GraphEnginePage />} />
                    <Route path="/metrics" element={<MetricsPage />} />
                    <Route path="/analysis" element={<AnalysisPage />} />
                    <Route path="/topology" element={<TopologyPage />} />
                    <Route path="/graphrag" element={<GraphRAGPage />} />
                </Routes>
                <footer className="border-t border-gray-200 py-6 text-center bg-white">
                    <p className="text-xs text-gray-400 tracking-wider">
                        FinOps AI Platform — AWS Architecture Intelligence powered by GraphRAG
                    </p>
                </footer>
            </div>
        </Router>
    )
}
