import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import DashboardPage from './pages/DashboardPage'
import GraphEnginePage from './pages/GraphEnginePage'
import AnalysisPage from './pages/AnalysisPage'

export default function App() {
    return (
        <Router>
            <div className="min-h-screen bg-gray-50">
                <Navbar />
                <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/graph" element={<GraphEnginePage />} />
                    <Route path="/analysis" element={<AnalysisPage />} />
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
