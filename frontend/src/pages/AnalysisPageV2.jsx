import React, { useState, useEffect, useCallback } from 'react';
import { 
  RecommendationCard, 
  SavingsSummary, 
  RecommendationHistory 
} from './components/RecommendationCard';

/**
 * Updated Analysis Page
 * - Displays stylish recommendation cards
 * - Shows total savings at top
 * - Implements refresh with background status tracking
 * - Shows recommendation history on click
 * - Polls for background task progress
 */
export function AnalysisPageWithRecommendations() {
  const [recommendations, setRecommendations] = useState([]);
  const [totalSavings, setTotalSavings] = useState(0);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);
  const [architectureId, setArchitectureId] = useState(null);
  const [architectureFile, setArchitectureFile] = useState(null);

  // Polling interval for task status
  const POLL_INTERVAL = 1000; // 1 second

  // Load recommendations (with cache)
  const loadRecommendations = useCallback(async (useCache = true) => {
    if (!architectureId && !architectureFile) return;

    setLoading(true);
    try {
      const response = await fetch('/api/recommendations/generate-bg', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          architecture_id: architectureId,
          architecture_file: architectureFile,
          use_cache: useCache,
        }),
      });

      const data = await response.json();

      if (data.source === 'cache') {
        // Instant result from cache
        setRecommendations(data.recommendations || []);
        setTotalSavings(data.total_estimated_savings || 0);
        setTaskId(null);
        setTaskStatus(null);
        await loadHistory();
      } else {
        // Background task started
        setTaskId(data.task_id);
        setTaskStatus({ state: 'queued', progress: 0 });
        setRecommendations([]);
      }
    } catch (error) {
      console.error('Failed to load recommendations:', error);
    } finally {
      setLoading(false);
    }
  }, [architectureId, architectureFile]);

  // Poll task status
  useEffect(() => {
    if (!taskId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`/api/recommendations/task-status/${taskId}`);
        const status = await response.json();

        setTaskStatus(status);

        // When complete, load results
        if (status.state === 'SUCCESS') {
          setRecommendations(status.result?.recommendations || []);
          setTotalSavings(status.result?.total_estimated_savings || 0);
          await loadHistory();
          clearInterval(pollInterval);
          setTaskId(null);
        }

        // Handle error
        if (status.state === 'FAILURE') {
          console.error('Task failed:', status.error);
          clearInterval(pollInterval);
          setTaskId(null);
        }
      } catch (error) {
        console.error('Failed to poll task:', error);
        clearInterval(pollInterval);
      }
    }, POLL_INTERVAL);

    return () => clearInterval(pollInterval);
  }, [taskId, loadHistory]);

  // Load recommendation history
  const loadHistory = useCallback(async () => {
    if (!architectureId && !architectureFile) return;

    try {
      const params = new URLSearchParams();
      if (architectureId) params.append('architecture_id', architectureId);
      if (architectureFile) params.append('architecture_file', architectureFile);

      const response = await fetch(`/api/recommendations/history?${params}`);
      const data = await response.json();

      setHistory(data.history || []);
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  }, [architectureId, architectureFile]);

  // Handle refresh button
  const handleRefresh = async () => {
    // Clear cache first
    await fetch('/api/recommendations/cache/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        architecture_id: architectureId,
        architecture_file: architectureFile,
      }),
    });

    // Then generate fresh
    await loadRecommendations(false);
  };

  // Load initial data
  useEffect(() => {
    loadRecommendations(true);
  }, [architectureId, architectureFile]);

  // Handle history item click
  const handleHistorySelect = async (historyItem) => {
    console.log('Selected history item:', historyItem);
    // Could navigate to detail view or reload that specific result
  };

  return (
    <div className="analysis-page">
      {/* Savings Summary at Top */}
      <div className="page-header">
        <SavingsSummary
          totalMonthly={totalSavings}
          totalAnnual={totalSavings * 12}
          recommendationCount={recommendations.length}
          status={
            taskId ? (taskStatus?.state === 'PROGRESS' ? 'generating' : 'idle')
              : (recommendations.length > 0 ? 'completed' : 'idle')
          }
        />

        {/* Controls */}
        <div className="page-controls">
          <button
            className="btn-refresh"
            onClick={handleRefresh}
            disabled={loading || !!taskId}
            title="Clear cache and generate fresh recommendations"
          >
            🔄 Refresh Analysis
          </button>

          <button
            className="btn-history"
            onClick={() => setShowHistory(!showHistory)}
            title="View past recommendation runs"
          >
            📋 History {history.length > 0 && `(${history.length})`}
          </button>

          {taskId && taskStatus && (
            <div className="task-progress">
              <span className="progress-label">{taskStatus.stage}</span>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${taskStatus.progress || 0}%` }}
                ></div>
              </div>
              <span className="progress-percent">{taskStatus.progress || 0}%</span>
            </div>
          )}
        </div>
      </div>

      {/* Recommendation History */}
      {showHistory && (
        <RecommendationHistory
          recommendations={history}
          onSelect={handleHistorySelect}
          loading={!history || history.length === 0}
        />
      )}

      {/* Recommendations Grid */}
      {recommendations && recommendations.length > 0 ? (
        <div className="recommendations-grid">
          {recommendations.map((rec, idx) => (
            <RecommendationCard
              key={rec.id || idx}
              recommendation={rec}
              totalSavingsPerMonth={totalSavings}
              onExpand={(card) => console.log('Expanded:', card)}
            />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          {loading || taskId ? (
            <p>⏳ Generating recommendations...</p>
          ) : (
            <p>No recommendations available. Click "Refresh Analysis" to get started.</p>
          )}
        </div>
      )}
    </div>
  );
}

// Export for use in routes
export default AnalysisPageWithRecommendations;
