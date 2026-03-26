import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import './StyledRecommendationCard.css';

/**
 * Styled Recommendation Card Component
 * Uses Uiverse design template with carousel and pagination
 */
export function StyledRecommendationCard({ recommendation, onViewDetails }) {
  const savingsPerMonth = recommendation.total_estimated_savings || 0;
  const savingsPerYear = savingsPerMonth * 12;
  
  // Extract key features from recommendation
  const title = recommendation.title || 'Cost Optimization';
  const description = recommendation.description || 
    recommendation.resource_identification?.service_type || 
    'AWS Optimization';
  
  const handleViewDetails = (e) => {
    e.preventDefault();
    if (onViewDetails) {
      onViewDetails(recommendation);
    }
  };
  
  const features = [];
  
  // Add savings as first feature
  if (savingsPerMonth > 0) {
    features.push(`Save $${savingsPerMonth.toFixed(0)}/month`);
  }
  
  // Add resource service type
  if (recommendation.resource_identification?.service_type) {
    features.push(recommendation.resource_identification.service_type);
  }
  
  // Add severity
  if (recommendation.severity) {
    features.push(`${recommendation.severity.toUpperCase()} Priority`);
  }
  
  // Add implementation complexity
  if (recommendation.implementation_complexity) {
    features.push(`${recommendation.implementation_complexity} Effort`);
  }

  const graphCtx = recommendation.graph_context || {};
  const cost = recommendation.cost_breakdown || {};
  const res = recommendation.resource_identification || {};
  const steps = recommendation.recommendations?.[0]?.implementation_steps || [];

  return (
    <div className="plan-shell">
      <div className="plan">
        <div className="plan__border" />

        <div className="card_title__container">
          <span className="card_title">{title}</span>
          <p className="card_paragraph">{description}</p>
        </div>

        <hr className="line" />

        <ul className="card__list">
          {features.slice(0, 5).map((feature, idx) => (
            <li key={idx} className="card__list_item">
              <span className="check">✓</span>
              <span className="list_text">{feature}</span>
            </li>
          ))}
        </ul>

        <div className="pricing">
          <span>
            ${savingsPerMonth.toFixed(0)}<small>/mo</small>
          </span>
          <span className="yearly">${savingsPerYear.toFixed(0)}/yr</span>
        </div>

        <div className="action">
          <a className="button" href="#" onClick={handleViewDetails}>
            View Details
          </a>
        </div>
      </div>

      <aside className="plan-drawer">
        <div className="plan-drawer__border" />
        <div className="plan-drawer__body">
          <h4 className="drawer-title">Recommendation Details</h4>
          <p className="drawer-sub">{res.service_type || 'AWS'} · {res.resource_id || 'N/A'}</p>

          <div className="drawer-section">
            <h5>Financial Snapshot</h5>
            <ul>
              <li>Current Cost: ${(cost.current_monthly || 0).toFixed(2)}/mo</li>
              <li>Projected Savings: ${savingsPerMonth.toFixed(2)}/mo</li>
              <li>Annual Impact: ${savingsPerYear.toFixed(2)}</li>
            </ul>
          </div>

          {(graphCtx.blast_radius_pct > 0 || graphCtx.dependency_count > 0 || graphCtx.is_spof) && (
            <div className="drawer-section">
              <h5>Graph Context</h5>
              <ul>
                {graphCtx.blast_radius_pct > 0 && <li>Blast Radius: {graphCtx.blast_radius_pct}%</li>}
                {graphCtx.dependency_count > 0 && <li>Dependencies: {graphCtx.dependency_count}</li>}
                {graphCtx.cross_az_count > 0 && <li>Cross-AZ Links: {graphCtx.cross_az_count}</li>}
                {graphCtx.is_spof && <li>Single Point of Failure</li>}
              </ul>
            </div>
          )}

          {steps.length > 0 && (
            <div className="drawer-section drawer-highlight">
              <h5>Implementation Steps</h5>
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
