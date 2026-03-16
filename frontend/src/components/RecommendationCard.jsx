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
  
  const severityColor = {
    critical: '#ED4B4B',
    high: '#F66B35',
    medium: '#FFC045',
    low: '#4CAF50',
  };
  
  const severityBg = {
    critical: '#FFE5E5',
    high: '#FFE8D6',
    medium: '#FFF8DC',
    low: '#E8F5E9',
  };
  
  const complexity = recommendation.implementation_complexity || 'medium';
  const category = recommendation.category || 'optimization';
  const severity = recommendation.severity || 'medium';
  
  const handleExpand = () => {
    setShowDetails(!showDetails);
    if (onExpand) onExpand(recommendation);
  };

  return (
    <div className="recommendation-plan">
      <div className="plan-inner">
        {/* Savings Badge */}
        <div className="plan-savings">
          <span className="savings-amount">
            ${savingsPerMonth.toFixed(0)}
            <small>/mo</small>
          </span>
          <span className="savings-year">${savingsPerYear.toFixed(0)}/year</span>
        </div>

        {/* Severity & Category Badges */}
        <div className="plan-badges">
          <span 
            className="badge severity" 
            style={{ 
              backgroundColor: severityColor[severity],
              color: '#fff',
              fontSize: '0.75rem'
            }}
          >
            {severity.toUpperCase()}
          </span>
          <span className="badge category">{category.replace(/-/g, ' ').toUpperCase()}</span>
          <span className="badge complexity">{complexity}</span>
        </div>

        {/* Main Title & Resource */}
        <h3 className="plan-title">
          {recommendation.title || `Recommendation #${recommendation.priority}`}
        </h3>
        
        <p className="plan-resource">
          <strong>Resource:</strong>{' '}
          {recommendation.resource_identification?.resource_id || 'N/A'}
        </p>

        {/* Quick Info */}
        {!showDetails && (
          <p className="plan-summary">
            {recommendation.resource_identification?.service_type && 
              `${recommendation.resource_identification.service_type} - `
            }
            Optimize for cost efficiency
          </p>
        )}

        {/* Expanded Details */}
        {showDetails && (
          <div className="plan-details">
            <div className="detail-section">
              <h4>Resource Details</h4>
              <ul>
                <li><strong>Service Type:</strong> {recommendation.resource_identification?.service_type || 'N/A'}</li>
                <li><strong>Region:</strong> {recommendation.resource_identification?.region || 'N/A'}</li>
                <li><strong>Environment:</strong> {recommendation.resource_identification?.environment || 'prod'}</li>
              </ul>
            </div>

            {/* Cost Breakdown */}
            {recommendation.cost_breakdown && (
              <div className="detail-section">
                <h4>Cost Breakdown</h4>
                <div className="cost-items">
                  <div className="cost-row">
                    <span>Current Monthly Cost:</span>
                    <strong>${(recommendation.cost_breakdown.current_monthly || 0).toFixed(2)}</strong>
                  </div>
                  {recommendation.cost_breakdown.line_items?.length > 0 && (
                    <div className="line-items">
                      {recommendation.cost_breakdown.line_items.slice(0, 3).map((item, idx) => (
                        <div key={idx} className="line-item">
                          <span>{item.description}</span>
                          <span className="amount">${item.cost?.toFixed(2) || '0.00'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Inefficiencies */}
            {recommendation.inefficiencies?.length > 0 && (
              <div className="detail-section">
                <h4>Issues Detected</h4>
                <ul>
                  {recommendation.inefficiencies.slice(0, 3).map((issue, idx) => (
                    <li key={idx}>
                      <strong>{issue.title}:</strong> {issue.root_cause}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Implementation Steps */}
            {recommendation.recommendations?.length > 0 && (
              <div className="detail-section">
                <h4>Action Plan</h4>
                <ol>
                  {recommendation.recommendations[0]?.implementation_steps?.slice(0, 4).map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {/* Performance & Risk */}
            <div className="detail-row">
              {recommendation.recommendations?.[0]?.performance_impact && (
                <div className="detail-box">
                  <strong>Performance Impact:</strong>
                  <p>{recommendation.recommendations[0].performance_impact}</p>
                </div>
              )}
              {recommendation.risk_level && (
                <div className="detail-box">
                  <strong>Risk Level:</strong>
                  <p>{recommendation.risk_level}</p>
                </div>
              )}
            </div>

            {/* Best Practice */}
            {recommendation.finops_best_practice && (
              <div className="detail-section bg-info">
                <h4>💡 AWS FinOps Best Practice</h4>
                <p>{recommendation.finops_best_practice}</p>
              </div>
            )}
          </div>
        )}

        {/* Action Button */}
        <div className="plan-action">
          <button 
            className="plan-button"
            onClick={handleExpand}
          >
            {showDetails ? 'Hide Details' : 'View Details'} →
          </button>
        </div>
      </div>
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
