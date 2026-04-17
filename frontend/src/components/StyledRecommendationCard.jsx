import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import './StyledRecommendationCard.css';

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
      badgeText = 'AI Validated';
    } else {
      badgeClass += ' source-badge--engine';
      badgeText = 'Engine';
    }
  } else {
    if (isRejected) {
      badgeClass += ' source-badge--rejected';
      badgeText = 'AI Insight';
    } else if (isConflict) {
      badgeClass += ' source-badge--conflict';
      badgeText = 'Conflict';
    } else {
      badgeClass += ' source-badge--llm';
      badgeText = 'AI Proposed';
    }
  }
  
  return (
    <div className={badgeClass}>
      <span className="source-badge__text">{badgeText}</span>
      {confidence > 0 && (
        <span className="source-badge__confidence">{confidencePercent}%</span>
      )}
    </div>
  );
}

/**
 * Styled Recommendation Card Component
 * Uses Uiverse design template with carousel and pagination
 */
export function StyledRecommendationCard({ recommendation, onViewDetails }) {
  const source = recommendation.source || 'engine';
  const isLLM = source === 'llm_proposed' || source === 'llm';
  const validationStatus = recommendation.validation_status;
  const engineConfidence = recommendation.engine_confidence;
  const llmConfidence = recommendation.llm_confidence;
  const savingsPerMonth = recommendation.total_estimated_savings || 0;
  const savingsPerYear = savingsPerMonth * 12;
  const hasSavings = savingsPerMonth > 0;
  const confScore = recommendation.confidence_score || 0;
  const confLabel = confScore >= 70 ? 'High' : confScore >= 40 ? 'Medium' : 'Low';
  
  const title = recommendation.title || (isLLM ? 'AI Security Insight' : 'Cost Optimization');
  const description = recommendation.description || 
    recommendation.resource_identification?.service_type || 
    (isLLM ? 'Architecture Review' : 'AWS Optimization');
  
  const handleViewDetails = (e) => {
    e.preventDefault();
    if (onViewDetails) onViewDetails(recommendation);
  };

  // Build features list — different for engine vs LLM
  const features = [];
  if (!isLLM && hasSavings) {
    features.push(`Save $${savingsPerMonth.toFixed(0)}/month`);
  }
  if (isLLM) {
    const cat = (recommendation.category || 'security').replace(/_/g, ' ');
    features.push(`${cat.charAt(0).toUpperCase() + cat.slice(1)} Finding`);
  }
  if (recommendation.resource_identification?.service_type) {
    features.push(recommendation.resource_identification.service_type);
  }
  if (recommendation.severity) {
    features.push(`${recommendation.severity.toUpperCase()} Priority`);
  }
  if (recommendation.implementation_complexity) {
    features.push(`${recommendation.implementation_complexity} Effort`);
  }
  if (confScore > 0) {
    features.push(`${confLabel} Confidence (${confScore}%)`);
  }

  const graphCtx = recommendation.graph_context || {};
  const cost = recommendation.cost_breakdown || {};
  const res = recommendation.resource_identification || {};
  const steps = recommendation.recommendations?.[0]?.implementation_steps || [];

  // Card theme class
  const planClass = isLLM ? 'plan plan--ai-insight' : 'plan plan--engine';
  const buttonClass = isLLM ? 'button button--ai' : 'button button--engine';
  const drawerClass = isLLM ? 'plan-drawer plan-drawer--ai' : 'plan-drawer';

  return (
    <div className="plan-shell">
      <div className={planClass}>
        <div className="plan__border" />

        <div className="card_title__container">
          <div className="card_title__header">
            <span className="card_title">{title}</span>
            <SourceBadge 
              source={source}
              validationStatus={validationStatus}
              engineConfidence={engineConfidence}
              llmConfidence={llmConfidence}
            />
          </div>
          <p className="card_paragraph">{description}</p>
        </div>

        <hr className="line" />

        <ul className="card__list">
          {features.slice(0, 5).map((feature, idx) => (
            <li key={idx} className="card__list_item">
              <span className={isLLM ? 'check check--ai' : 'check'}>{'✓'}</span>
              <span className="list_text">{feature}</span>
            </li>
          ))}
        </ul>

        {/* Pricing: only show for engine cards with real savings */}
        {!isLLM && hasSavings ? (
          <div className="pricing">
            <span>${savingsPerMonth.toFixed(0)}<small>/mo</small></span>
            <span className="yearly">${savingsPerYear.toFixed(0)}/yr</span>
          </div>
        ) : isLLM ? (
          <div className="pricing pricing--ai">
            <span className="ai-finding-label">{(recommendation.category || 'security').replace(/_/g, ' ').toUpperCase()}</span>
            <span className="ai-confidence-pill">{confLabel}</span>
          </div>
        ) : (
          <div className="pricing pricing--neutral">
            <span className="neutral-label">Optimization</span>
          </div>
        )}

        <div className="action">
          <a className={buttonClass} href="#" onClick={handleViewDetails}>
            {isLLM ? 'View AI Insight' : 'View Details'}
          </a>
        </div>
      </div>

      <aside className={drawerClass}>
        <div className="plan-drawer__border" />
        <div className="plan-drawer__body">
          <h4 className="drawer-title">{isLLM ? 'AI Insight Details' : 'Recommendation Details'}</h4>
          <p className="drawer-sub">{res.service_type || 'AWS'} · {res.resource_id || res.resource_name || 'N/A'}</p>

          {/* Financial snapshot — only for engine cards with costs */}
          {!isLLM && (cost.current_monthly > 0 || hasSavings) && (
            <div className="drawer-section">
              <h5>Financial Snapshot</h5>
              <ul>
                {cost.current_monthly > 0 && <li>Current Cost: ${(cost.current_monthly).toFixed(2)}/mo</li>}
                {hasSavings && <li>Projected Savings: ${savingsPerMonth.toFixed(2)}/mo</li>}
                {hasSavings && <li>Annual Impact: ${savingsPerYear.toFixed(2)}</li>}
              </ul>
            </div>
          )}

          {(graphCtx.blast_radius_pct > 0 || graphCtx.dependency_count > 0 || graphCtx.is_spof) && (
            <div className="drawer-section">
              <h5>{isLLM ? 'Architecture Impact' : 'Graph Context'}</h5>
              <ul>
                {graphCtx.blast_radius_pct > 0 && <li>Blast Radius: {graphCtx.blast_radius_pct}%</li>}
                {graphCtx.dependency_count > 0 && <li>Dependencies: {graphCtx.dependency_count}</li>}
                {graphCtx.cross_az_count > 0 && <li>Cross-AZ Links: {graphCtx.cross_az_count}</li>}
                {graphCtx.is_spof && <li>Single Point of Failure</li>}
              </ul>
            </div>
          )}

          {steps.length > 0 && (
            <div className={isLLM ? 'drawer-section drawer-highlight--ai' : 'drawer-section drawer-highlight'}>
              <h5>{isLLM ? 'Remediation Steps' : 'Implementation Steps'}</h5>
              <ol>
                {steps.slice(0, 4).map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

/**
 * Recommendation Cards Carousel with Pagination
 * Displays styled cards side-by-side with navigation
 */
export function RecommendationCarousel({ recommendations = [], onViewDetails }) {
  const [currentPage, setCurrentPage] = useState(0);
  const [cardsPerPage, setCardsPerPage] = useState(3);

  // Update cards per page based on screen size
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setCardsPerPage(1);
      } else if (window.innerWidth < 1200) {
        setCardsPerPage(2);
      } else {
        setCardsPerPage(3);
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const totalPages = Math.ceil(recommendations.length / cardsPerPage);
  const startIdx = currentPage * cardsPerPage;
  const visibleCards = recommendations.slice(startIdx, startIdx + cardsPerPage);

  // Keep page index valid when cards-per-page or total recommendations change.
  useEffect(() => {
    if (totalPages === 0) {
      setCurrentPage(0);
      return;
    }
    if (currentPage > totalPages - 1) {
      setCurrentPage(totalPages - 1);
    }
  }, [currentPage, totalPages]);

  const handlePrevPage = () => {
    setCurrentPage(prev => (prev > 0 ? prev - 1 : totalPages - 1));
  };

  const handleNextPage = () => {
    setCurrentPage(prev => (prev < totalPages - 1 ? prev + 1 : 0));
  };

  const handleDotClick = (pageIdx) => {
    setCurrentPage(pageIdx);
  };

  if (!recommendations || recommendations.length === 0) {
    return (
      <div className="recommendations-carousel">
        <p style={{ textAlign: 'center', color: '#697e91', padding: '2rem' }}>
          No recommendations available
        </p>
      </div>
    );
  }

  return (
    <div className="recommendations-carousel">
      {/* Cards Container */}
      <div className="recommendations-cards-wrapper">
        {visibleCards.map((rec, idx) => (
          <StyledRecommendationCard 
            key={rec.id || `${startIdx}-${idx}`} 
            recommendation={rec}
            onViewDetails={onViewDetails}
          />
        ))}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="pagination-controls">
          <div className="pagination-buttons">
            <button
              className="pagination-btn"
              onClick={handlePrevPage}
              title="Previous page"
            >
              <ChevronLeft size={18} />
            </button>

            <span className="pagination-page-chip">
              {currentPage + 1} / {totalPages}
            </span>

            <button
              className="pagination-btn"
              onClick={handleNextPage}
              title="Next page"
            >
              <ChevronRight size={18} />
            </button>
          </div>

          {/* Dot Indicators */}
          <div className="pagination-dots">
            {Array.from({ length: totalPages }).map((_, idx) => (
              <div
                key={idx}
                className={`dot ${idx === currentPage ? 'active' : ''}`}
                onClick={() => handleDotClick(idx)}
                title={`Go to page ${idx + 1}`}
              />
            ))}
          </div>

          {/* Card Count */}
          <span className="pagination-total-chip">
            <span className="total-chip-number">{recommendations.length}</span>
            optimization recommendations
          </span>
        </div>
      )}
    </div>
  );
}

export default RecommendationCarousel;
