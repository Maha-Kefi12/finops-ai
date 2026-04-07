import React, { useState } from 'react';
import './RecommendationCard.css';

/**
 * Stylish Recommendation Card Component
 * Displays individual recommendations with click-to-expand details
 */
/**
 * Source Badge Component - Identifies recommendation source
 */
function SourceBadge({ source, validationStatus, engineConfidence, llmConfidence }) {
  const isEngineBacked = source === 'engine' || source === 'engine_backed';
  const isValidated = validationStatus === 'validated';
  const isRejected = validationStatus === 'rejected';
  const isConflict = validationStatus === 'conflict';
  
  const confidence = engineConfidence || llmConfidence || 0;
  const confidencePercent = Math.round(confidence * 100);
  
  let badgeClass = 'source-badge';
  let badgeIcon = '';
  let badgeText = '';
  
  if (isEngineBacked) {
    if (isValidated) {
      badgeClass += ' source-badge--ai-validated';
      badgeIcon = '🤖✓';
      badgeText = 'AI Validated';
    } else {
      badgeClass += ' source-badge--engine';
      badgeIcon = '⚙️';
      badgeText = 'Engine';
    }
  } else {
    if (isRejected) {
      badgeClass += ' source-badge--rejected';
      badgeIcon = '💡✗';
      badgeText = 'AI Insight';
    } else if (isConflict) {
      badgeClass += ' source-badge--conflict';
      badgeIcon = '⚠️';
      badgeText = 'Conflict';
    } else {
      badgeClass += ' source-badge--llm';
      badgeIcon = '🤖';
      badgeText = 'AI Proposed';
    }
  }
  
  return (
    <div className={badgeClass}>
      <span className="source-badge__icon">{badgeIcon}</span>
      <span className="source-badge__text">{badgeText}</span>
      {confidence > 0 && (
        <span className="source-badge__confidence">{confidencePercent}%</span>
      )}
    </div>
  );
}

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
  
  // Two-tier system fields
  const source = recommendation.source || 'engine';
  const validationStatus = recommendation.validation_status;
  const engineConfidence = recommendation.engine_confidence;
  const llmConfidence = recommendation.llm_confidence;
  const validationNotes = recommendation.validation_notes;

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
          <div className="rec-card__header-top">
            <span className="rec-card__title">{recommendation.title || `Recommendation #${recommendation.priority}`}</span>
            <SourceBadge 
              source={source}
              validationStatus={validationStatus}
              engineConfidence={engineConfidence}
              llmConfidence={llmConfidence}
            />
          </div>
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
              <h5>FinOps Best Practice</h5>
              <p>{recommendation.finops_best_practice}</p>
            </div>
          )}

          {validationNotes && (
            <div className="drawer-section drawer-validation">
              <h5>Validation Notes</h5>
              <p>{validationNotes}</p>
            </div>
          )}

          <div className="drawer-section drawer-aws-style">
            <h5>AWS FinOps Framework</h5>
            <div className="aws-pillars">
              <span className="aws-pillar">💰 Cost Optimization</span>
              <span className="aws-pillar">📊 Usage Optimization</span>
              <span className="aws-pillar">⚡ Performance Efficiency</span>
            </div>
          </div>
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
