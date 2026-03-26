import React, { useState } from 'react';
import './RecommendationCard.css';

/**
 * Stylish Recommendation Card Component
 * Displays individual recommendations with click-to-expand details
 */
export function RecommendationCard({ 
  recommendation, 
  onExpand,
  isExpanded,
  totalSavingsPerMonth 
}) {
  const [showDetails, setShowDetails] = useState(isExpanded || false);
  
  const savingsPerMonth = recommendation.total_estimated_savings || 0;
  const savingsPerYear = savingsPerMonth * 12;
  
  const complexity = recommendation.implementation_complexity || 'medium';
  const category = recommendation.category || 'optimization';
  const severity = recommendation.severity || 'medium';
  const serviceType = recommendation.resource_identification?.service_type || 'AWS Service';
  const resourceId = recommendation.resource_identification?.resource_id || 'N/A';
  const summary = recommendation.recommendations?.[0]?.description
    || recommendation.recommendations?.[0]?.action
    || 'Optimization opportunity identified for this resource.';

  const listItems = [
    `Service: ${serviceType}`,
    `Resource: ${resourceId}`,
    `Potential savings: $${savingsPerMonth.toFixed(0)}/mo`,
    `Priority: ${String(recommendation.priority || 'N/A')}`,
    `Risk: ${String(severity).toUpperCase()}`,
  ];
  
  const handleExpand = () => {
    setShowDetails(!showDetails);
    if (onExpand) onExpand(recommendation);
  };

  return (
    <div className={`rec-card-shell ${showDetails ? 'is-pinned' : ''}`}>
      <article className="rec-card">
        <div className="rec-card__border" />

        <div className="rec-card__header">
          <span className="rec-card__title">{recommendation.title || `Recommendation #${recommendation.priority}`}</span>
          <p className="rec-card__paragraph">{summary}</p>
        </div>

        <hr className="rec-card__line" />

        <div className="rec-card__chips">
          <span className={`chip severity ${String(severity).toLowerCase()}`}>{String(severity).toUpperCase()}</span>
          <span className="chip category">{category.replace(/-/g, ' ')}</span>
          <span className="chip complexity">{complexity}</span>
        </div>

        <ul className="rec-card__list">
          {listItems.map((item, idx) => (
            <li key={idx} className="rec-card__list_item">
              <span className="rec-card__check">✓</span>
              <span className="rec-card__list_text">{item}</span>
            </li>
          ))}
        </ul>

        <div className="rec-card__savings">
          <span className="monthly">${savingsPerMonth.toFixed(0)} / month</span>
          <span className="yearly">${savingsPerYear.toFixed(0)} / year</span>
        </div>

        <button className="rec-card__button" onClick={handleExpand}>
          {showDetails ? 'Pin Off' : 'Pin Details'}
        </button>
      </article>

      <aside className="rec-card-drawer">
        <div className="rec-card-drawer__border" />
        <div className="rec-card-drawer__body">
          <h4 className="drawer-title">Recommendation Details</h4>
          <p className="drawer-sub">{serviceType} · {resourceId}</p>

          <div className="drawer-section">
            <h5>Resource</h5>
            <ul>
              <li><strong>Region:</strong> {recommendation.resource_identification?.region || 'N/A'}</li>
              <li><strong>Environment:</strong> {recommendation.resource_identification?.environment || 'prod'}</li>
              <li><strong>Current Cost:</strong> ${(recommendation.cost_breakdown?.current_monthly || 0).toFixed(2)}/mo</li>
            </ul>
          </div>

          {recommendation.recommendations?.length > 0 && (
            <div className="drawer-section">
              <h5>Action Plan</h5>
              <ol>
                {recommendation.recommendations[0]?.implementation_steps?.slice(0, 4).map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ol>
            </div>
          )}

          {recommendation.finops_best_practice && (
            <div className="drawer-section drawer-highlight">
              <h5>Best Practice</h5>
              <p>{recommendation.finops_best_practice}</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

/**
 * Recommendation History Component
 * Shows past recommendations with timestamp and status
 */
export function RecommendationHistory({ 
  recommendations, 
  onSelect,
  loading = false 
}) {
  if (loading) {
    return (
      <div className="history-container">
        <p className="loading-text">Loading recommendation history...</p>
      </div>
    );
  }

  if (!recommendations || recommendations.length === 0) {
    return (
      <div className="history-container">
        <p className="empty-text">No recommendation history yet</p>
      </div>
    );
  }

  return (
    <div className="history-container">
      <h3 className="history-title">📋 Recommendation History</h3>
      <div className="history-list">
        {recommendations.map((rec, idx) => (
          <div 
            key={rec.id || idx} 
            className="history-item"
            onClick={() => onSelect && onSelect(rec)}
          >
            <div className="history-header">
              <span className="history-date">
                {new Date(rec.created_at).toLocaleDateString()} 
                {' '}
                <span className="history-time">
                  {new Date(rec.created_at).toLocaleTimeString()}
                </span>
              </span>
              <span className={`history-status ${rec.status}`}>
                {rec.status === 'completed' ? '✓ Completed' : '✗ Failed'}
              </span>
            </div>
            <div className="history-meta">
              <span className="history-cards">{rec.card_count} recommendations</span>
              <span className="history-savings">
                💰 ${rec.total_estimated_savings?.toFixed(0) || 0}/mo
              </span>
              <span className="history-time-info">{rec.generation_time_ms}ms</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Overall Savings Display Component
 */
export function SavingsSummary({ 
  totalMonthly = 0, 
  totalAnnual = 0,
  recommendationCount = 0,
  status = 'idle' // idle | generating | completed | failed
}) {
  return (
    <div className="savings-summary">
      <div className="savings-card main">
        <h2 className="savings-title">💰 Total Potential Savings</h2>
        <div className="savings-amount-large">
          ${totalMonthly.toFixed(0)}<span className="savings-period">/month</span>
        </div>
        <div className="savings-annual">
          ${totalAnnual.toFixed(0)} per year
        </div>
        <div className="savings-meta">
          <span className="meta-item">
            {recommendationCount} recommendations
          </span>
          <span className={`meta-status ${status}`}>
            {status === 'generating' && '⏳ Analyzing...'}
            {status === 'completed' && '✓ Ready'}
            {status === 'failed' && '✗ Error'}
            {status === 'idle' && '○ Idle'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default RecommendationCard;
