import React, { useState, useRef, useEffect } from 'react';
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

  return (
    <div className="plan">
      <div className="inner">
        <span className="pricing">
          <span>
            ${savingsPerMonth.toFixed(0)}<small>/mo</small>
          </span>
        </span>
        
        <p className="title">{title}</p>
        
        <p className="info">
          {description}
        </p>
        
        <ul className="features">
          {features.slice(0, 3).map((feature, idx) => (
            <li key={idx}>
              <span className="icon">
                <svg height="24" width="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M0 0h24v24H0z" fill="none"></path>
                  <path fill="currentColor" d="M10 15.172l9.192-9.193 1.415 1.414L10 18l-6.364-6.364 1.414-1.414z"></path>
                </svg>
              </span>
              <span>{feature}</span>
            </li>
          ))}
        </ul>
        
        <div className="action">
          <a className="button" href="#" onClick={handleViewDetails}>
            View Details
          </a>
        </div>
      </div>
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
  const scrollContainerRef = useRef(null);

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

  const handlePrevPage = () => {
    setCurrentPage(prev => (prev > 0 ? prev - 1 : totalPages - 1));
  };

  const handleNextPage = () => {
    setCurrentPage(prev => (prev < totalPages - 1 ? prev + 1 : 0));
  };

  const handleDotClick = (pageIdx) => {
    setCurrentPage(pageIdx);
  };

  // Scroll to show cards smoothly
  useEffect(() => {
    if (scrollContainerRef.current) {
      const scrollAmount = startIdx * 330; // Approximate card width + gap
      scrollContainerRef.current.scrollLeft = scrollAmount;
    }
  }, [startIdx]);

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
      <div className="recommendations-cards-wrapper" ref={scrollContainerRef}>
        {recommendations.map((rec, idx) => (
          <StyledRecommendationCard 
            key={rec.id || idx} 
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

            <span className="pagination-info">
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
          <span className="pagination-info">
            Showing {startIdx + 1}-{Math.min(startIdx + cardsPerPage, recommendations.length)} of {recommendations.length}
          </span>
        </div>
      )}
    </div>
  );
}

export default RecommendationCarousel;
