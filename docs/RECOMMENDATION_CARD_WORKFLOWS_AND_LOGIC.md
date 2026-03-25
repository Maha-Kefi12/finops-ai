# FinOps AI System: Recommendation Card Workflows & Logic - Complete Guide

**Document Version:** 2.0  
**Last Updated:** March 2026  
**Scope:** Comprehensive documentation of recommendation card display, state management, user interactions, and rendering logic

## Table of Contents

1. [System Overview](#system-overview)
2. [Data Structure & Props](#data-structure--props)
3. [Recommendation Card Architecture](#recommendation-card-architecture)
4. [State Management Flow](#state-management-flow)
5. [View Modes: Carousel vs Grid](#view-modes-carousel-vs-grid)
6. [Rendering Pipeline](#rendering-pipeline)
7. [User Interaction Handlers](#user-interaction-handlers)
8. [Styling & Visual Design](#styling--visual-design)
9. [Animation & Transitions](#animation--transitions)
10. [Pagination & Navigation Logic](#pagination--navigation-logic)
11. [Responsive Design & Breakpoints](#responsive-design--breakpoints)
12. [Performance Optimization](#performance-optimization)
13. [Error Handling & Edge Cases](#error-handling--edge-cases)

---

## System Overview

The recommendation card system transforms backend API recommendations into an interactive, responsive UI that progressively discloses information:

```
Summary Card (low details)
    ↓ [Click "View Details"]
Expanded Card (medium details)
    ↓ [Scroll down]
Full Details Panel (all information)
```

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Backend API Response                         │
│           (Recommendations array + Summary data)                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────▼─────────────────┐
              │ AnalysisPage / AnalysisPageV2│
              │ (Main container component)   │
              └────────────┬─────────────────┘
                           │
        ┌──────────────────┼──────────────────────────┐
        │                  │                          │
   ┌────▼──────────┐  ┌───▼─────────────┐  ┌────────▼────┐
   │ Summary Stats │  │ Carousel/Grid   │  │  History    │
   │ Bar           │  │ Recommendation  │  │  Panel      │
   │               │  │ Cards           │  │             │
   └───────────────┘  └───┬─────────────┘  └─────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────▼────────┐ ┌────▼────────┐ ┌────▼────────┐
    │ Card 1      │ │ Card 2      │ │ Card 3      │
    │ Summary     │ │ Summary     │ │ Summary     │
    │             │ │             │ │             │
    │ [Details ▼] │ │ [Details ▼] │ │ [Details ▼] │
    └────┬────────┘ └────┬────────┘ └────┬────────┘
         │                │                │
    ┌────▼────────────────▼────────────────▼────┐
    │  Expanded Card Panel (if any clicked)     │
    │                                           │
    │  ┌─────────────────────────────────────┐ │
    │  │ Full Details View                   │ │
    │  │ • All recommendation data           │ │
    │  │ • Cost breakdown table              │ │
    │  │ • Implementation steps              │ │
    │  │ • Resource details                  │ │
    │  └─────────────────────────────────────┘ │
    └───────────────────────────────────────────┘
```

---

## Data Structure & Props

### Complete Recommendation Data Object

When the API returns recommendations, each item has this structure:

```json
{
  "id": 1,
  "title": "Right-size under-utilized EC2 instances",
  "priority": 1,
  "priority_label": "CRITICAL",
  "severity": "critical",
  "category": "compute-right-sizing",
  "category_display": "Compute Right-Sizing",
  
  "summary": "Stop and right-size 8 m5.xlarge instances that are running at average CPU 15% and memory 12%",
  
  "resource_identification": {
    "resource_count": 8,
    "resource_type": "EC2_INSTANCE",
    "resource_details": [
      {
        "resource_id": "i-0123456789abcdef0",
        "region": "us-east-1",
        "current_type": "m5.xlarge",
        "recommended_type": "t3.large",
        "current_monthly_cost": 156.00,
        "recommended_monthly_cost": 58.00,
        "monthly_savings": 98.00,
        "current_utilization": {
          "cpu_percent": 15,
          "memory_percent": 12
        }
      }
    ]
  },
  
  "total_estimated_savings": 784.00,
  "estimated_savings_currency": "USD",
  "estimated_savings_period": "monthly",
  "implementation_complexity": "medium",
  "risk_level": "low",
  
  "inefficiencies": [
    {
      "type": "over-provisioning",
      "description": "Instances oversized for actual workload",
      "impact": "Wasting $784/month on compute capacity not being used"
    }
  ],
  
  "implementation_plan": {
    "prerequisites": [
      "Ensure instances have EBS optimization enabled",
      "Create AMI backup before any changes",
      "Notify application teams of planned changes"
    ],
    "steps": [
      {
        "step_number": 1,
        "title": "Create AMI snapshot",
        "description": "Create Machine Image (AMI) of current instance configuration",
        "estimated_time_minutes": 5
      },
      {
        "step_number": 2,
        "title": "Launch new right-sized instance",
        "description": "Launch new t3.large instance from AMI",
        "estimated_time_minutes": 3
      }
    ],
    "total_estimated_time_minutes": 15,
    "estimated_downtime_minutes": 2
  },
  
  "finops_best_practices": [
    {
      "practice": "Right-sizing of compute",
      "description": "Regularly analyze utilization patterns and adjust instance types",
      "reference_url": "https://aws.amazon.com/architecture/well-architected/"
    }
  ],
  
  "related_resources": ["i-0123456789abcdef0", "i-0987654321fedcba0"],
  "aws_service": "ec2",
  "is_actionable": true,
  "requires_approval": false
}
```

### RecommendationCard Props Interface

```typescript
interface RecommendationCardProps {
  // Data
  recommendation: RecommendationObject;
  index: number;
  
  // State
  isExpanded: boolean;
  
  // Callbacks
  onViewDetails: (index: number) => void;
  onApprove?: (recommendation: RecommendationObject) => void;
  
  // Configuration
  viewMode?: "carousel" | "grid" | "list";
  showApprovalButton?: boolean;
  theme?: "light" | "dark";
}
```

### StyledRecommendationCard Props (Carousel)

```typescript
interface StyledRecommendationCardProps {
  recommendation: RecommendationObject;
  isSelected: boolean;
  onClick: () => void;
  isDarkMode?: boolean;
}
```

### RecommendationCarousel Props

```typescript
interface RecommendationCarouselProps {
  recommendations: RecommendationObject[];
  onViewDetails: (index: number, recommendation: RecommendationObject) => void;
  loading?: boolean;
  isDarkMode?: boolean;
}
```

---

## Recommendation Card Architecture

### Component Hierarchy

```
AnalysisPage
├── SummaryStatsBar
│   ├── TotalSavingsCard
│   ├── RecommendationCountCard
│   ├── CriticalIssuesCard
│   └── ImplementationTimeCard
│
├── RecommendationCarousel (Primary View)
│   ├── CardNavigation
│   │   ├── PrevButton
│   │   ├── DotPagination
│   │   └── NextButton
│   │
│   └── CarouselViewport
│       ├── StyledRecommendationCard (Card 1)
│       │   ├── SeverityIndicator
│       │   ├── CardHeader (title + category)
│       │   ├── SavingsDisplay
│       │   ├── ServiceInfo
│       │   └── ViewDetailsButton
│       │
│       ├── StyledRecommendationCard (Card 2)
│       └── StyledRecommendationCard (Card 3)
│
├── ExpandedDetailsPanel (conditional)
│   ├── FullRecommendationCard
│   │   ├── CardHeader
│   │   ├── IdentificationSection
│   │   │   └── ResourceTable
│   │   ├── ImplementationSection
│   │   │   └── StepsList
│   │   ├── BestPracticesSection
│   │   └── ActionButtons
│   │
│   └── CloseButton
│
└── HistoryPanel
    ├── PreviousAnalysis
    └── Comparison
```

### File Locations

```
frontend/src/
├── components/
│   ├── analysis/
│   │   ├── AnalysisPage.jsx                    ← Main container
│   │   ├── AnalysisPageV2.jsx                  ← Grid view
│   │   ├── SummaryStatsBar.jsx
│   │   ├── HistoryPanel.jsx
│   │   └── styles/
│   │       └── analysis.module.css
│   │
│   ├── recommendations/
│   │   ├── RecommendationCard.jsx              ← Single card (summary)
│   │   ├── FullRecommendationCard.jsx          ← Expanded view
│   │   ├── StyledRecommendationCard.jsx        ← Carousel card
│   │   ├── RecommendationCarousel.jsx          ← Carousel container
│   │   ├── ResourceTable.jsx
│   │   ├── ImplementationSteps.jsx
│   │   └── styles/
│   │       ├── recommendation-card.module.css
│   │       ├── styled-card.css
│   │       └── carousel.css
│   │
│   └── common/
│       ├── SeverityBadge.jsx
│       ├── CategoryTag.jsx
│       └── CostDisplay.jsx
│
├── hooks/
│   ├── useRecommendationExpand.js             ← Expansion logic
│   ├── useCarouselPagination.js               ← Carousel logic
│   └── useResponsive.js                       ← Window resize handling
│
└── utils/
    ├── formatters.js                          ← $ formatting, dates
    └── colorScheme.js                         ← Severity colors
```

---

## State Management Flow

### AnalysisPage Component State

```javascript
// src/components/analysis/AnalysisPage.jsx

function AnalysisPage() {
  // ========== DATA STATE ==========
  const [recResult, setRecResult] = useState(null);
  // {
  //   recommendations: [RecommendationObject, ...],
  //   total_potential_monthly_savings: 12345.67,
  //   total_recommendations: 15,
  //   by_priority: { CRITICAL: 2, HIGH: 5, ... }
  // }
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // ========== UI STATE ==========
  const [expandedCards, setExpandedCards] = useState(new Set());
  // Track which card indices are expanded
  // Example: Set [ 0 ] means card at index 0 is expanded
  
  const [currentPage, setCurrentPage] = useState(0);
  // Current page in carousel (0-indexed)
  
  const [cardsPerPage, setCardsPerPage] = useState(3);
  // How many cards fit in viewport (responsive)
  
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  // ========== EFFECTS ==========
  useEffect(() => {
    // On component mount: fetch analysis
    fetchAnalysis();
  }, []);
  
  useEffect(() => {
    // On window resize: recalculate cardsPerPage
    const handleResize = () => {
      const width = window.innerWidth;
      if (width < 768) setCardsPerPage(1);
      else if (width < 1024) setCardsPerPage(2);
      else setCardsPerPage(3);
    };
    
    window.addEventListener("resize", handleResize);
    handleResize(); // Call on mount
    return () => window.removeEventListener("resize", handleResize);
  }, []);
  
  // ========== HANDLERS ==========
  const handleViewDetails = (index) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index); // Toggle off
      } else {
        newSet.add(index);    // Toggle on
      }
      return newSet;
    });
    
    // Scroll expanded card into view
    setTimeout(() => {
      const element = document.getElementById(`expanded-${index}`);
      element?.scrollIntoView({ behavior: "smooth" });
    }, 300);
  };
  
  const handleCarouselNext = () => {
    const maxPages = Math.ceil(recResult.recommendations.length / cardsPerPage);
    setCurrentPage(prev => (prev + 1) % maxPages);
  };
  
  const handleCarouselPrev = () => {
    const maxPages = Math.ceil(recResult.recommendations.length / cardsPerPage);
    setCurrentPage(prev => (prev - 1 + maxPages) % maxPages);
  };
  
  const handlePageDotClick = (pageNum) => {
    setCurrentPage(pageNum);
  };
  
  const fetchAnalysis = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: getAccountId(),
          region: getRegion()
        })
      });
      const data = await response.json();
      setRecResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  // ========== RENDER ==========
  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBoundary error={error} onRetry={fetchAnalysis} />;
  if (!recResult) return null;
  
  return (
    <div className="analysis-page">
      <SummaryStatsBar stats={recResult} />
      
      <div className="recommendations-container">
        <RecommendationCarousel
          recommendations={recResult.recommendations}
          currentPage={currentPage}
          cardsPerPage={cardsPerPage}
          onNext={handleCarouselNext}
          onPrev={handleCarouselPrev}
          onPageDot={handlePageDotClick}
          onViewDetails={handleViewDetails}
          expandedCards={expandedCards}
          isDarkMode={isDarkMode}
        />
        
        {/* Render expanded cards inline */}
        {Array.from(expandedCards).map(index => (
          <FullRecommendationCard
            key={`expanded-${index}`}
            id={`expanded-${index}`}
            recommendation={recResult.recommendations[index]}
            onClose={() => handleViewDetails(index)}
          />
        ))}
      </div>
      
      <HistoryPanel />
    </div>
  );
}
```

### State Update Flow Diagram

```
User Action → Handler Called → State Updated → Component Re-renders
    ↓
User clicks "View Details"
    ↓
handleViewDetails(index) called
    ↓
setExpandedCards(prev => { ... })
    ↓
React re-renders AnalysisPage
    ↓
expandedCards Set passed to children
    ↓
FullRecommendationCard rendered (conditional)
    ↓
Smooth scroll animation triggers
    ↓
User scrolls down → Sees expanded details
```

---

## View Modes: Carousel vs Grid

### Carousel View (Primary - AnalysisPage.jsx)

**When used:** Default view for most users

**Props:**
```javascript
<RecommendationCarousel
  recommendations={recResult.recommendations}    // Full array
  currentPage={currentPage}                      // Current page (0-indexed)
  cardsPerPage={cardsPerPage}                    // 1, 2, or 3
  onNext={handleCarouselNext}                    // Pagination handler
  onPrev={handleCarouselPrev}
  onPageDot={handlePageDotClick}
  onViewDetails={handleViewDetails}
  expandedCards={expandedCards}                  // Set of expanded indices
  isDarkMode={isDarkMode}
/>
```

**Rendering Logic:**
```javascript
// RecommendationCarousel.jsx

function RecommendationCarousel({
  recommendations,
  currentPage,
  cardsPerPage,
  onNext,
  onPrev,
  onPageDot,
  onViewDetails,
  expandedCards,
  isDarkMode
}) {
  // Calculate which cards to display on current page
  const startIndex = currentPage * cardsPerPage;
  const endIndex = startIndex + cardsPerPage;
  const visibleCards = recommendations.slice(startIndex, endIndex);
  const totalPages = Math.ceil(recommendations.length / cardsPerPage);
  
  // Pad with empty slots if needed (for consistent layout)
  while (visibleCards.length < cardsPerPage) {
    visibleCards.push(null);
  }
  
  return (
    <div className="carousel-container">
      {/* Cards Viewport */}
      <div className="carousel-viewport">
        <div className="carousel-cards-grid">
          {visibleCards.map((rec, idx) => {
            if (!rec) {
              return <div key={`empty-${idx}`} className="card-placeholder" />;
            }
            
            const actualIndex = startIndex + idx;
            return (
              <StyledRecommendationCard
                key={rec.id}
                recommendation={rec}
                isSelected={expandedCards.has(actualIndex)}
                onClick={() => onViewDetails(actualIndex)}
                isDarkMode={isDarkMode}
              />
            );
          })}
        </div>
      </div>
      
      {/* Navigation */}
      <div className="carousel-navigation">
        <button onClick={onPrev} className="nav-button prev">
          ← Previous
        </button>
        
        <div className="dot-pagination">
          {Array.from({ length: totalPages }, (_, i) => (
            <button
              key={i}
              className={`dot ${i === currentPage ? "active" : ""}`}
              onClick={() => onPageDot(i)}
            />
          ))}
        </div>
        
        <button onClick={onNext} className="nav-button next">
          Next →
        </button>
      </div>
    </div>
  );
}
```

**Visual Layout:**
```
┌─────────────────────────────────────────────────────┐
│ ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│ │  Card 1  │  │  Card 2  │  │  Card 3  │  Page 1/5 │
│ │          │  │          │  │          │           │
│ │[Details]│  │[Details] │  │[Details] │           │
│ └──────────┘  └──────────┘  └──────────┘           │
│                                                     │
│   ← Previous  ● ● ● ○ ○  Next →                    │
└─────────────────────────────────────────────────────┘
```

### Grid View (Alternative - AnalysisPageV2.jsx)

**When used:** Alternative view, showing all cards simultaneously

**Rendering Logic:**
```javascript
// AnalysisPageV2.jsx

function AnalysisPageV2() {
  const [recResult, setRecResult] = useState(null);
  const [expandedCards, setExpandedCards] = useState(new Set());
  
  const handleViewDetails = (index) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      newSet.has(index) ? newSet.delete(index) : newSet.add(index);
      return newSet;
    });
  };
  
  return (
    <div className="analysis-grid">
      <SummaryStatsBar stats={recResult} />
      
      <div className="grid-container">
        {recResult.recommendations.map((rec, idx) => (
          <div key={rec.id} className="grid-item">
            <RecommendationCard
              recommendation={rec}
              index={idx}
              isExpanded={expandedCards.has(idx)}
              onViewDetails={handleViewDetails}
            />
            
            {expandedCards.has(idx) && (
              <FullRecommendationCard
                recommendation={rec}
                onClose={() => handleViewDetails(idx)}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

**CSS Grid Setup:**
```css
/* grid-container with auto-fill responsive columns */
.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
  padding: 20px;
}

@media (max-width: 768px) {
  .grid-container {
    grid-template-columns: 1fr;
  }
}
```

---

## Rendering Pipeline

### Step 1: API Response → State Update

```javascript
const fetchAnalysis = async () => {
  const response = await fetch("/api/analyze", { ... });
  const data = await response.json();
  
  // Data structure from backend:
  // {
  //   status: "success",
  //   recommendations: [
  //     { id: 1, title: "...", ... },
  //     { id: 2, title: "...", ... },
  //     ...
  //   ],
  //   summary: {
  //     total_potential_monthly_savings: 12345.67,
  //     total_recommendations: 15,
  //     by_priority: { CRITICAL: 2, HIGH: 5, MEDIUM: 4, LOW: 4 }
  //   }
  // }
  
  setRecResult(data);  // Triggers re-render
};
```

### Step 2: Component Re-render with New Props

```javascript
// RecommendationCarousel receives props from AnalysisPage
render(
  <RecommendationCarousel
    recommendations={recResult.recommendations}  // Pass array
    currentPage={0}                              // Initial page
    cardsPerPage={3}
    onViewDetails={handleViewDetails}
    expandedCards={new Set()}                    // Empty initially
    ...
  />
)
```

### Step 3: Data Transformation for Display

```javascript
// Within RecommendationCarousel or StyledRecommendationCard

const displayData = {
  // From API data:
  title: recommendation.title,
  severity: recommendation.severity,  // "critical" | "high" | "medium" | "low"
  category: recommendation.category,  // "compute-right-sizing", etc.
  
  // Transformations for display:
  savingsFormatted: formatCurrency(recommendation.total_estimated_savings),
  // "$12,345.67/mo" ← From "$12345.67"
  
  severityColor: colorMap[recommendation.severity],
  // "red" ← From "critical"
  
  categoryIcon: categoryIcons[recommendation.category],
  // "cpu" icon ← From "compute-right-sizing"
  
  estimatedTime: `${recommendation.implementation_plan.total_estimated_time_minutes} min`,
  // "15 min" ← From 15
};
```

### Step 4: JSX Rendering

```javascript
// StyledRecommendationCard.jsx

function StyledRecommendationCard({ recommendation, isSelected, onClick }) {
  return (
    <div className={`card ${isSelected ? "selected" : ""}`} onClick={onClick}>
      {/* Header with severity indicator */}
      <div className="card-header">
        <div className={`severity-indicator ${recommendation.severity}`} />
        <h3 className="card-title">{recommendation.title}</h3>
      </div>
      
      {/* Savings - most prominent */}
      <div className="savings-display">
        <span className="label">Monthly Savings</span>
        <span className="amount">
          ${recommendation.total_estimated_savings.toLocaleString('en-US', { maximumFractionDigits: 2 })}
        </span>
      </div>
      
      {/* Service/Category info */}
      <div className="card-meta">
        <span className={`category-badge ${recommendation.category}`}>
          {recommendation.category_display}
        </span>
      </div>
      
      {/* Call-to-action */}
      <button className="details-button">
        View Details ▼
      </button>
    </div>
  );
}
```

### Step 5: User Interaction → Expansion

```javascript
// When user clicks "View Details":

const handleClick = () => {
  // Toggle expanded state
  setExpandedCards(prev => {
    const newSet = new Set(prev);
    data.isExpanded ? newSet.delete(cardIndex) : newSet.add(cardIndex);
    return newSet;
  });
  
  // Trigger animation + scroll
  setTimeout(() => {
    document.getElementById(`expanded-${cardIndex}`).scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  }, 0);
};
```

### Step 6: Expanded Card Rendering

```javascript
// FullRecommendationCard renders AFTER summary card

const ExpandedCard = ({ recommendation, isExpanded }) => {
  if (!isExpanded) return null;  // Not rendered if collapsed
  
  return (
    <div className="expanded-card" style={{
      maxHeight: isExpanded ? "1000px" : "0px",
      overflow: "hidden",
      transition: "max-height 0.3s ease-in-out"
    }}>
      {/* Resource identification table */}
      <ResourceTable resources={recommendation.resource_identification.resource_details} />
      
      {/* Implementation steps */}
      <ImplementationSteps plan={recommendation.implementation_plan} />
      
      {/* Best practices */}
      <BestPracticesPanel practices={recommendation.finops_best_practices} />
    </div>
  );
};
```

---

## User Interaction Handlers

### 1. View Details / Expand Card

```javascript
const handleViewDetails = (cardIndex) => {
  // Toggle expansion
  const isCurrentlyExpanded = expandedCards.has(cardIndex);
  
  const newExpandedCards = new Set(expandedCards);
  if (isCurrentlyExpanded) {
    newExpandedCards.delete(cardIndex);
  } else {
    newExpandedCards.add(cardIndex);
  }
  
  setExpandedCards(newExpandedCards);
  
  // Scroll expanded card into view (after animation completes)
  if (!isCurrentlyExpanded) {
    setTimeout(() => {
      const element = document.getElementById(`expanded-card-${cardIndex}`);
      if (element) {
        element.scrollIntoView({
          behavior: "smooth",
          block: "nearest"
        });
      }
    }, 300);
  }
};
```

### 2. Carousel Navigation - Next Page

```javascript
const handleCarouselNext = () => {
  const totalRecs = recResult.recommendations.length;
  const totalPages = Math.ceil(totalRecs / cardsPerPage);
  
  setCurrentPage(prev => {
    const nextPage = (prev + 1) % totalPages;
    return nextPage;
  });
  
  // Optional: Close any expanded cards when navigating
  setExpandedCards(new Set());
};
```

### 3. Carousel Navigation - Previous Page

```javascript
const handleCarouselPrev = () => {
  const totalRecs = recResult.recommendations.length;
  const totalPages = Math.ceil(totalRecs / cardsPerPage);
  
  setCurrentPage(prev => {
    const prevPage = (prev - 1 + totalPages) % totalPages;
    return prevPage;
  });
  
  // Optional: Close expanded cards
  setExpandedCards(new Set());
};
```

### 4. Pagination Dot Click

```javascript
const handleDotClick = (pageNumber) => {
  // Validate page number
  const totalPages = Math.ceil(recResult.recommendations.length / cardsPerPage);
  if (pageNumber >= 0 && pageNumber < totalPages) {
    setCurrentPage(pageNumber);
    setExpandedCards(new Set()); // Close expanded
  }
};
```

### 5. Collapse Expanded Card

```javascript
const handleCloseExpanded = (cardIndex) => {
  setExpandedCards(prev => {
    const newSet = new Set(prev);
    newSet.delete(cardIndex);
    return newSet;
  });
};
```

### 6. Responsive Window Resize

```javascript
useEffect(() => {
  const handleWindowResize = () => {
    const width = window.innerWidth;
    
    // Calculate optimal cards per page
    let newCardsPerPage = 3;
    if (width < 768) {
      newCardsPerPage = 1;  // Mobile
    } else if (width < 1024) {
      newCardsPerPage = 2;  // Tablet
    }
    
    setCardsPerPage(newCardsPerPage);
    
    // Reset to page 0 if current page is now out of bounds
    const totalPages = Math.ceil(recResult.recommendations.length / newCardsPerPage);
    if (currentPage >= totalPages) {
      setCurrentPage(0);
    }
  };
  
  window.addEventListener("resize", handleWindowResize);
  return () => window.removeEventListener("resize", handleWindowResize);
}, [recResult, currentPage, cardsPerPage]);
```

### 7. Copy Recommendation to Clipboard

```javascript
const handleCopyRecommendation = async (recommendation) => {
  const text = `
${recommendation.title}
Priority: ${recommendation.priority_label}
Savings: $${recommendation.total_estimated_savings}/month

${recommendation.summary}

Implementation: ${recommendation.implementation_plan.total_estimated_time_minutes} minutes
  `.trim();
  
  try {
    await navigator.clipboard.writeText(text);
    showToast("Copied to clipboard");
  } catch (err) {
    console.error("Failed to copy:", err);
  }
};
```

### 8. Approve / Implement Recommendation

```javascript
const handleApproveRecommendation = async (recommendation) => {
  try {
    const response = await fetch("/api/recommendations/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recommendation_id: recommendation.id,
        approved_at: new Date().toISOString()
      })
    });
    
    if (response.ok) {
      showToast(`Approved: ${recommendation.title}`);
      // Optionally refresh analysis
      fetchAnalysis();
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
};
```

---

## Styling & Visual Design

### Color Scheme System

```javascript
// src/utils/colorScheme.js

const SEVERITY_COLORS = {
  critical: {
    bg: "#FEE2E2",      // Light red
    border: "#DC2626",  // Medium red
    text: "#991B1B",    // Dark red
    dot: "#EF4444"      // Bright red
  },
  high: {
    bg: "#FEF3C7",      // Light amber
    border: "#F59E0B",  // Medium amber
    text: "#92400E",    // Dark amber
    dot: "#FBBF24"      // Bright amber
  },
  medium: {
    bg: "#DBEAFE",      // Light blue
    border: "#3B82F6",  // Medium blue
    text: "#1E3A8A",    // Dark blue
    dot: "#60A5FA"      // Bright blue
  },
  low: {
    bg: "#DCFCE7",      // Light green
    border: "#22C55E",  // Medium green
    text: "#166534",    // Dark green
    dot: "#4ADE80"      // Bright green
  }
};

const CATEGORY_COLORS = {
  "compute-right-sizing": { bg: "#F3E8FF", accent: "#A78BFA", icon: "cpu" },
  "storage-optimization": { bg: "#E0F2FE", accent: "#38BDF8", icon: "hdd" },
  "database-optimization": { bg: "#F0FDF4", accent: "#86EFAC", icon: "database" },
  "network-optimization": { bg: "#FEF3C7", accent: "#FBBF24", icon: "network" },
  "reserved-instances": { bg: "#FCE7F3", accent: "#F472B6", icon: "purchase" },
  "waste-elimination": { bg: "#FECACA", accent: "#EF4444", icon: "trash" }
};

export const getColorByCode = (code, colorType = "severity") => {
  const colorMap = colorType === "severity" ? SEVERITY_COLORS : CATEGORY_COLORS;
  return colorMap[code] || colorMap.low;
};
```

### CSS Module Structure

```css
/* src/components/recommendations/styles/recommendation-card.module.css */

.card {
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  border-left: 4px solid var(--severity-color);
}

.card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.card.selected {
  border-left-width: 6px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.severity-indicator {
  width: 3px;
  height: 24px;
  border-radius: 2px;
  background: var(--severity-dot-color);
  flex-shrink: 0;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: #1F2937;
  margin: 0;
}

.savings-display {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--category-bg);
  border-radius: 4px;
}

.savings-display .label {
  font-size: 12px;
  font-weight: 500;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.savings-display .amount {
  font-size: 24px;
  font-weight: 700;
  color: var(--severity-text);
}

.card-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.category-badge {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 12px;
  background: var(--category-bg);
  color: var(--category-accent);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.details-button {
  align-self: flex-start;
  padding: 8px 12px;
  background: var(--severity-border);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.details-button:hover {
  background: var(--severity-text);
  transform: translateX(2px);
}
```

### Tailwind + CSS Hybrid Approach

```javascript
// Some components use Tailwind classes, others use CSS modules

// Tailwind:
<div className="p-4 bg-gray-50 rounded-lg border-l-4 border-red-500">
  {children}
</div>

// CSS Module:
<div className={styles.card}>
  {children}
</div>

// Hybrid:
<div className={`${styles.card} ${isDarkMode ? 'dark-mode' : ''}`}>
  {children}
</div>
```

---

## Animation & Transitions

### Expand/Collapse Animation

```css
/* Smooth expand/collapse with max-height transition */
.expanded-card {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.expanded-card.open {
  max-height: 2000px;  /* Large enough for any content */
  opacity: 1;
}
```

### CSS Transition Timings

```css
/* Fast interactions (user feedback) */
.button:hover {
  transition: all 0.15s ease-out;
}

/* Medium interactions (UI state changes) */
.card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Slow interactions (content expansion) */
.expanded-panel {
  transition: max-height 0.5s ease-in-out;
}
```

### Carousel Slide Animation

```javascript
// When currentPage changes, smooth scroll cards into view

const carouselViewport = useRef(null);

useEffect(() => {
  if (carouselViewport.current) {
    const scrollAmount = startIndex * cardWidth;
    carouselViewport.current.scrollTo({
      left: scrollAmount,
      behavior: "smooth"
    });
  }
}, [currentPage, cardsPerPage]);
```

### Skeleton Loading Animation

```css
@keyframes shimmer {
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
}

.skeleton-card {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
  border-radius: 8px;
}
```

---

## Pagination & Navigation Logic

### Carousel Pagination Calculation

```javascript
function calculatePaginationState(recommendations, cardsPerPage, currentPage) {
  const totalRecs = recommendations.length;
  const totalPages = Math.ceil(totalRecs / cardsPerPage);
  
  const startIndex = currentPage * cardsPerPage;
  const endIndex = Math.min(startIndex + cardsPerPage, totalRecs);
  const visibleRecs = recommendations.slice(startIndex, endIndex);
  
  return {
    totalPages,
    startIndex,
    endIndex,
    visibleRecs,
    hasNextPage: currentPage < totalPages - 1,
    hasPrevPage: currentPage > 0,
    pageInfo: `${currentPage + 1} of ${totalPages}`
  };
}
```

### Dot Pagination Rendering

```javascript
function DotPagination({ totalPages, currentPage, onDotClick }) {
  return (
    <div className="dot-pagination">
      {Array.from({ length: totalPages }, (_, i) => (
        <button
          key={i}
          className={`dot ${i === currentPage ? "active" : ""}`}
          onClick={() => onDotClick(i)}
          aria-label={`Go to page ${i + 1}`}
          aria-current={i === currentPage ? "page" : undefined}
        />
      ))}
    </div>
  );
}

// CSS for dots:
.dot-pagination {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 16px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #D1D5DB;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.dot:hover {
  border-color: #9CA3AF;
  background: #E5E7EB;
}

.dot.active {
  background: #3B82F6;
  border-color: #3B82F6;
}
```

### Keyboard Navigation

```javascript
// Optional: Enable arrow key navigation

useEffect(() => {
  const handleKeyDown = (e) => {
    if (e.key === "ArrowRight") {
      handleCarouselNext();
    } else if (e.key === "ArrowLeft") {
      handleCarouselPrev();
    }
  };
  
  window.addEventListener("keydown", handleKeyDown);
  return () => window.removeEventListener("keydown", handleKeyDown);
}, [currentPage]);
```

---

## Responsive Design & Breakpoints

### Breakpoint System

```javascript
// src/utils/breakpoints.js

export const BREAKPOINTS = {
  mobile: 480,
  tablet: 768,
  desktop: 1024,
  wide: 1280
};

export function getResponsiveCardsPerPage(width) {
  if (width < BREAKPOINTS.tablet) return 1;      // Mobile
  if (width < BREAKPOINTS.desktop) return 2;     // Tablet
  return 3;                                       // Desktop+
}

export function getResponsiveGridColumns(width) {
  if (width < BREAKPOINTS.mobile) return 1;
  if (width < BREAKPOINTS.tablet) return 1;
  if (width < BREAKPOINTS.desktop) return 2;
  if (width < BREAKPOINTS.wide) return 3;
  return 4;
}
```

### Responsive CSS

```css
/* Mobile: Full width, single column */
@media (max-width: 767px) {
  .carousel-viewport {
    aspect-ratio: auto;
    height: auto;
  }
  
  .carousel-card {
    width: 100%;
  }
  
  .card-title {
    font-size: 14px;
  }
  
  .savings-display .amount {
    font-size: 18px;
  }
  
  .carousel-navigation {
    flex-direction: column;
    gap: 12px;
  }
  
  .nav-button {
    width: 100%;
  }
}

/* Tablet: 2 columns */
@media (min-width: 768px) and (max-width: 1023px) {
  .carousel-viewport {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }
  
  .card {
    width: 100%;
  }
}

/* Desktop: 3 columns */
@media (min-width: 1024px) {
  .carousel-viewport {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }
}

/* Large screens: Wider cards */
@media (min-width: 1280px) {
  .card {
    max-width: 400px;
  }
}
```

---

## Performance Optimization

### Memoization to Prevent Unnecessary Re-renders

```javascript
// Wrap card component to prevent re-renders when props haven't changed
import { memo } from "react";

const RecommendationCardMemo = memo(
  function RecommendationCard({ recommendation, isExpanded, onViewDetails }) {
    return (
      // Card JSX
    );
  },
  (prevProps, nextProps) => {
    // Custom comparison: Only re-render if important props change
    return (
      prevProps.recommendation.id === nextProps.recommendation.id &&
      prevProps.isExpanded === nextProps.isExpanded
    );
  }
);

export default RecommendationCardMemo;
```

### Lazy Loading Large Lists

```javascript
import { useEffect, useState } from "react";

function LazyRecommendationsList({ recommendations }) {
  const [displayedCount, setDisplayedCount] = useState(10);
  const itemsPerBatch = 10;
  
  useEffect(() => {
    const handleScroll = () => {
      if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
        // Reached near bottom, load more
        setDisplayedCount(prev => prev + itemsPerBatch);
      }
    };
    
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);
  
  return (
    <div>
      {recommendations.slice(0, displayedCount).map((rec, idx) => (
        <RecommendationCard key={rec.id} recommendation={rec} index={idx} />
      ))}
      {displayedCount < recommendations.length && (
        <p>Loading more...</p>
      )}
    </div>
  );
}
```

### Virtual Scrolling for Large Lists (Windowing)

```javascript
// For 100+ recommendations, use virtual scrolling

import { FixedSizeList as List } from "react-window";

function VirtualizedRecommendationsList({ recommendations }) {
  const Row = ({ index, style }) => (
    <div style={style}>
      <RecommendationCard recommendation={recommendations[index]} />
    </div>
  );
  
  return (
    <List
      height={600}
      itemCount={recommendations.length}
      itemSize={250}
      width="100%"
    >
      {Row}
    </List>
  );
}
```

---

## Error Handling & Edge Cases

### Empty State

```javascript
if (!recResult || recResult.recommendations.length === 0) {
  return (
    <div className="empty-state">
      <EmptyIcon />
      <h3>No Recommendations Available</h3>
      <p>Your infrastructure is optimized, or analysis is still running.</p>
      <button onClick={fetchAnalysis}>Run New Analysis</button>
    </div>
  );
}
```

### Error State

```javascript
if (error) {
  return (
    <div className="error-state">
      <ErrorIcon />
      <h3>Analysis Error</h3>
      <p>{error}</p>
      <button onClick={fetchAnalysis}>Retry Analysis</button>
    </div>
  );
}
```

### Loading State

```javascript
if (loading) {
  return (
    <div className="loading-state">
      <div className="spinner" />
      <p>Analyzing your infrastructure...</p>
      <div className="progress-bar" style={{ width: "45%" }} />
    </div>
  );
}
```

### Invalid Card Index

```javascript
const handleViewDetails = (index) => {
  if (index < 0 || index >= recResult.recommendations.length) {
    console.warn(`Invalid card index: ${index}`);
    return;
  }
  
  setExpandedCards(prev => {
    const newSet = new Set(prev);
    newSet.has(index) ? newSet.delete(index) : newSet.add(index);
    return newSet;
  });
};
```

### Null/Undefined Recommendations

```javascript
function SafeRecommendationCard({ recommendation }) {
  if (!recommendation || typeof recommendation !== "object") {
    return (
      <div className="card card-error">
        Invalid recommendation data
      </div>
    );
  }
  
  return (
    // Render normally
  );
}
```

### Overflow Content Handling

```css
/* Prevent long text from breaking layout */
.card-title {
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.summary-text {
  max-height: 100px;
  overflow-y: auto;
  font-size: 13px;
}
```

---

## Summary: Complete Card Rendering Flow

```
1. Component Mount
   ↓ useEffect hook
   ↓ Call fetchAnalysis()

2. API Response Received
   ↓ setRecResult(data)
   ↓ State updated

3. Component Re-render
   ↓ Pass data to RecommendationCarousel
   ↓ Calculate visible cards (based on currentPage + cardsPerPage)

4. Cards Rendered
   ↓ 3 StyledRecommendationCard components
   ↓ Each shows summary (title, savings, severity)

5. User Interaction
   ↓ User clicks "View Details"
   ↓ handleViewDetails(index) called

6. State Update
   ↓ setExpandedCards(prev => { add index })
   ↓ Component re-renders

7. Expanded Card Rendered
   ↓ FullRecommendationCard appears below summary
   ↓ Shows all details (resources, steps, practices)

8. User sees:
   - Carousel of 3 cards
   - Dot pagination (page indicator)
   - Expanded details panel (if card expanded)
```

This architecture maintains a clean **separation of concerns**:
- **AnalysisPage** = State management + logic
- **RecommendationCarousel** = Pagination + layout
- **StyledRecommendationCard** = Summary display
- **FullRecommendationCard** = Detailed display

Each component is independently testable and reusable.

