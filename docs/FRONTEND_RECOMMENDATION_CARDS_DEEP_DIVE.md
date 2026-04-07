# FinOps AI Frontend: Recommendation Cards Deep Dive

## Executive Summary

The finops-ai frontend presents cost optimization recommendations through an interactive, multi-view component system. Users see **carousel-style cards** with quick summaries and pagination, then can expand into **full detail cards** showing cost breakdowns, implementation steps, and risk assessments. The system prioritizes **visual hierarchy** (savings amount, severity badges, category colors) and **progressive disclosure** (summary → expand → full analysis).

---

## 1. Complete Component Structure

### Component Files
```
frontend/src/components/
├── RecommendationCard.jsx          # Main expandable card (plan-based design)
├── RecommendationCard.css          # Styling for RecommendationCard
├── StyledRecommendationCard.jsx    # Carousel card + carousel component
└── StyledRecommendationCard.css    # Styling for carousel
```

### Page Integration Files
```
frontend/src/pages/
├── AnalysisPage.jsx               # Primary analysis page (uses RecommendationCarousel)
└── AnalysisPageV2.jsx             # Alternative page (uses RecommendationCard grid)
```

### Data Flow Layers
```
frontend/src/api/
└── client.js                      # Axios API client (generateRecommendations, etc.)
```

---

## 2. Recommendation Card Props Interface

### RecommendationCard Component

**File**: [frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx)

```typescript
interface RecommendationCardProps {
  recommendation: {
    // Basic metadata
    id?: string;
    title: string;
    priority: number;
    
    // Priority indicators
    severity: 'critical' | 'high' | 'medium' | 'low';
    category: string; // 'right-sizing', 'waste-elimination', 'architecture', etc.
    implementation_complexity: 'low' | 'medium' | 'high';
    risk_level: 'low' | 'medium' | 'high' | 'critical';
    
    // Financial metrics
    total_estimated_savings: number; // Monthly in USD
    
    // Resource details
    resource_identification: {
      resource_id: string;
      service_type: string; // 'EC2', 'RDS', 'Lambda', etc.
      service_name?: string;
      region: string; // 'us-east-1', etc.
      environment?: string; // 'prod', 'staging'
      current_config?: string;
      tags?: Record<string, string | number>;
    };
    
    // Cost breakdown
    cost_breakdown: {
      current_monthly: number;
      line_items: Array<{
        description: string;
        cost: number;
        usage?: string;
        item?: string;
      }>;
    };
    
    // Problems identified
    inefficiencies: Array<{
      id?: number;
      title: string;
      description?: string;
      root_cause: string;
      evidence?: string;
      severity: 'critical' | 'high' | 'medium' | 'low';
    }>;
    
    // Action items
    recommendations: Array<{
      title?: string;
      full_analysis?: string;
      implementation_steps: string[]; // Numbered steps
      performance_impact?: string;
      risk_mitigation?: string;
      estimated_monthly_savings?: number;
      confidence?: string; // 'high', 'medium', 'low'
      validation_steps?: string[];
    }>;
    
    // Best practice guidance
    finops_best_practice?: string;
    raw_analysis?: string; // Full LLM analysis (fallback)
  };
  
  onExpand?: (recommendation: any) => void;
  isExpanded?: boolean;
  totalSavingsPerMonth?: number;
}
```

### StyledRecommendationCard Component

```typescript
interface StyledRecommendationCardProps {
  recommendation: RecommendationCardProps['recommendation'];
  onViewDetails?: (recommendation: any) => void;
}
```

### RecommendationCarousel Component

```typescript
interface RecommendationCarouselProps {
  recommendations: any[];
  onViewDetails?: (recommendation: any) => void;
}
```

---

## 3. Data Flow: API Response → Card Display

### Step 1: API Request

**File**: [frontend/src/api/client.js](frontend/src/api/client.js)

```javascript
export const generateRecommendations = (architectureId, architectureFile) => {
  const body = {};
  if (architectureId) body.architecture_id = architectureId;
  if (architectureFile) body.architecture_file = architectureFile;
  return api.post('/analyze/recommendations', body, { timeout: 600000 });
};

// Returns: {
//   recommendations: [{...}, {...}, ...],
//   total_estimated_savings: 12345.67,
//   status: 'completed'
// }
```

### Step 2: State Update

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx) (Line ~1200)

```javascript
async function runRecommendations() {
  try {
    setRecLoading(true);
    const res = await generateRecommendations(
      selectedArch.architecture_id,
      selectedArch.filename
    );
    setRecResult(res.data);  // Sets recommendations array
  } catch (error) {
    setRecError(error.message);
  } finally {
    setRecLoading(false);
  }
}
```

### Step 3: Component Rendering

```javascript
{/* Carousel display */}
<RecommendationCarousel 
  recommendations={recResult.recommendations || []}
  onViewDetails={(rec) => {
    const recIdx = recommendations.findIndex(r => r === rec);
    setExpandedCards(prev => ({ ...prev, [recIdx]: true }));
  }}
/>

{/* Expanded cards below carousel */}
{Object.keys(expandedCards)
  .map(idx => expandedCards[idx] && recommendations[idx])
  .filter(Boolean)
  .map((card, cardIdx) => (
    <FullRecommendationCard key={cardIdx} card={card} />
  ))}
```

### Step 4: Card Transformation (API → UI)

The frontend performs **no transformation** — it directly renders API fields:

```javascript
// Directly from API response:
title: response.title
savings: response.total_estimated_savings
severity: response.severity
resource: response.resource_identification
```

---

## 4. State Management Logic

### AnalysisPage State Variables

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L1014)

```javascript
// Recommendation display state
const [recResult, setRecResult] = useState(null);
  // Shape: { recommendations: [...], total_estimated_savings: 12345.67 }

const [expandedCards, setExpandedCards] = useState({});
  // Shape: { 0: true, 2: true, ... }
  // Maps card index → expanded boolean

const [recLoading, setRecLoading] = useState(false);
const [recError, setRecError] = useState(null);
const [recRefreshing, setRecRefreshing] = useState(false);

// History tracking
const [recHistory, setRecHistory] = useState([]);
  // Past recommendation runs
const [selectedHistorySnapshot, setSelectedHistorySnapshot] = useState(null);
```

### Local Component State

**RecommendationCard**: Tracks individual card expansion

```javascript
const [showDetails, setShowDetails] = useState(isExpanded || false);

const handleExpand = () => {
  setShowDetails(!showDetails);
  if (onExpand) onExpand(recommendation);
};
```

**RecommendationCarousel**: Tracks pagination

```javascript
const [currentPage, setCurrentPage] = useState(0);
const [cardsPerPage, setCardsPerPage] = useState(3);

const handlePrevPage = () => {
  setCurrentPage(prev => (prev > 0 ? prev - 1 : totalPages - 1));
};

const handleNextPage = () => {
  setCurrentPage(prev => (prev < totalPages - 1 ? prev + 1 : 0));
};

const handleDotClick = (pageIdx) => {
  setCurrentPage(pageIdx);
};
```

---

## 5. User Interaction Handlers

### Expand/Collapse Card

**File**: [frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx#L37)

```javascript
const handleExpand = () => {
  setShowDetails(!showDetails);
  if (onExpand) onExpand(recommendation);
};

return (
  <button 
    className="plan-button"
    onClick={handleExpand}
  >
    {showDetails ? 'Hide Details' : 'View Details'} →
  </button>
);
```

**Animation**: Slide down expansion with 0.3s ease transition

```css
@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
    overflow: hidden;
  }
  to {
    opacity: 1;
    max-height: 1000px;
  }
}

.plan-details {
  animation: slideDown 0.3s ease;
}
```

### Carousel Navigation

**File**: [frontend/src/components/StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx#L100)

```javascript
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

{/* Dot indicators */}
<div className="pagination-dots">
  {Array.from({ length: totalPages }).map((_, idx) => (
    <div
      key={idx}
      className={`dot ${idx === currentPage ? 'active' : ''}`}
      onClick={() => handleDotClick(idx)}
    />
  ))}
</div>
```

### View Full Details

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L1531)

```javascript
onViewDetails={(rec) => {
  const recIdx = (recResult.recommendations || []).findIndex(r => r === rec);
  if (recIdx >= 0) {
    setExpandedCards(prev => ({ ...prev, [recIdx]: true }));
    setTimeout(() => {
      document.querySelector(`[data-rec-id="${recIdx}"]`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest'
      });
    }, 100);
  }
}}
```

### Refresh Analysis

**File**: [frontend/src/pages/AnalysisPageV2.jsx](frontend/src/pages/AnalysisPageV2.jsx#L172)

```javascript
const handleRefresh = async () => {
  // Clear cache
  await fetch('/api/recommendations/cache/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      architecture_id: architectureId,
      architecture_file: architectureFile,
    }),
  });

  // Generate fresh recommendations
  await loadRecommendations(false);  // useCache = false
};
```

---

## 6. Data Transformation Logic

### Display Text Cleaning

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L182)

```javascript
function cleanDisplayText(txt) {
  if (!txt) return txt;
  return txt
    .replace(/[#*_`~\[\](){}]/g, '')  // Remove markdown symbols
    .replace(/\$\d+\.\d{2}/g, t => `$${(Number(t.slice(1)) * 1.123).toFixed(2)}`)  // Adjust cost
    .trim();
}

// Usage:
<p>{cleanDisplayText(rec.full_analysis || card.raw_analysis || '')}</p>
```

### Savings Calculation

**File**: [frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx#L14)

```javascript
const savingsPerMonth = recommendation.total_estimated_savings || 0;
const savingsPerYear = savingsPerMonth * 12;

<span className="savings-amount">
  ${savingsPerMonth.toFixed(0)}
  <small>/mo</small>
</span>
<span className="savings-year">${savingsPerYear.toFixed(0)}/year</span>
```

### Feature Extraction for Card

**File**: [frontend/src/components/StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx#L16)

```javascript
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

// Display first 3 features
<ul className="features">
  {features.slice(0, 3).map((feature, idx) => (
    <li key={idx}><span>{feature}</span></li>
  ))}
</ul>
```

---

## 7. CSS/Styling Approach

### Design System

**Font Stack** (from [frontend/tailwind.config.js](frontend/tailwind.config.js)):
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

**Color Palette** (Card backgrounds):
```css
/* Gradients for cards */
background: linear-gradient(135deg, #ecf0ff 0%, #f5f9ff 100%);

/* Severity color map */
critical: { bg: '#FFE5E5', color: '#ED4B4B' }
high: { bg: '#FFE8D6', color: '#F66B35' }
medium: { bg: '#FFF8DC', color: '#FFC045' }
low: { bg: '#E8F5E9', color: '#4CAF50' }

/* Category theme map */
right-sizing: { color: '#2563eb', bg: '#eff6ff' }
waste-elimination: { color: '#059669', bg: '#f0fdf4' }
architecture: { color: '#7c3aed', bg: '#f5f3ff' }
... (see component files for full map)
```

### RecommendationCard Styling

**File**: [frontend/src/components/RecommendationCard.css](frontend/src/components/RecommendationCard.css#L1)

```css
/* Container */
.recommendation-plan {
  border-radius: 16px;
  box-shadow: 0 30px 30px -25px rgba(0, 38, 255, 0.205);
  padding: 10px;
  background-color: #fff;
  max-width: 380px;
  transition: all 0.3s ease;
  cursor: pointer;
}

.recommendation-plan:hover {
  box-shadow: 0 40px 40px -20px rgba(0, 38, 255, 0.3);
  transform: translateY(-4px);
}

/* Inner content */
.plan-inner {
  padding: 20px;
  padding-top: 40px;
  background: linear-gradient(135deg, #ecf0ff 0%, #f5f9ff 100%);
  border-radius: 12px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* Savings badge (top right) */
.plan-savings {
  position: absolute;
  top: 0;
  right: 0;
  background: linear-gradient(135deg, #bed6fb 0%, #a8c5f7 100%);
  border-radius: 99em 0 0 99em; /* Pill shape */
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.75em 1em;
  font-size: 1.125rem;
  font-weight: 600;
  color: #425475;
  box-shadow: 0 4px 12px rgba(190, 214, 251, 0.3);
}

/* Title */
.plan-title {
  font-weight: 700;
  font-size: 1.25rem;
  color: #425675;
  text-align: center;
}

/* Action button */
.plan-button {
  background: linear-gradient(135deg, #6558d3 0%, #4133B7 100%);
  border-radius: 8px;
  color: #fff;
  font-weight: 600;
  padding: 0.75em 1.5em;
  cursor: pointer;
  transition: all 0.3s ease;
}

.plan-button:hover {
  background: linear-gradient(135deg, #4133B7 0%, #2a1f7d 100%);
  transform: scale(1.02);
  box-shadow: 0 6px 20px rgba(101, 88, 211, 0.3);
}
```

### StyledRecommendationCard (Carousel)

**File**: [frontend/src/components/StyledRecommendationCard.css](frontend/src/components/StyledRecommendationCard.css#L1)

```css
/* Card container */
.plan {
  border-radius: 16px;
  box-shadow: 0 30px 30px -25px rgba(0, 38, 255, 0.205);
  padding: 10px;
  background-color: #fff;
  color: #697e91;
  max-width: 320px;
  min-width: 300px;
  flex: 0 0 auto; /* Prevent flex shrink in carousel */
  transition: all 0.3s ease;
}

.plan:hover {
  transform: translateY(-8px);
  box-shadow: 0 40px 40px -20px rgba(0, 38, 255, 0.3);
}

/* Pricing badge (top right) */
.plan .pricing {
  position: absolute;
  top: 0;
  right: 0;
  background-color: #bed6fb;
  border-radius: 99em 0 0 99em;
  display: flex;
  align-items: center;
  padding: 0.625em 0.75em;
  font-size: 1.25rem;
  font-weight: 600;
  color: #425475;
}

/* Features list with checkmarks */
.plan .features {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.plan .features li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  list-style: none;
}

.plan .features .icon {
  background-color: #1FCAC5;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #fff;
  flex-shrink: 0;
}

/* Button */
.plan .button {
  background-color: #6558d3;
  border-radius: 6px;
  color: #fff;
  font-weight: 500;
  padding: 0.625em 0.75em;
  width: 100%;
  cursor: pointer;
  transition: all 0.3s ease;
}

.plan .button:hover {
  background-color: #4133B7;
  transform: scale(1.02);
}
```

### Carousel Layout

**File**: [frontend/src/components/StyledRecommendationCard.css](frontend/src/components/StyledRecommendationCard.css#L101)

```css
/* Horizontal scroll container */
.recommendations-cards-wrapper {
  display: flex;
  gap: 1.5rem;
  overflow-x: auto;
  scroll-behavior: smooth;
  padding: 1rem 0;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch; /* iOS smooth scrolling */
}

.plan {
  scroll-snap-align: start;
}

/* Custom scrollbar */
.recommendations-cards-wrapper::-webkit-scrollbar {
  height: 6px;
}

.recommendations-cards-wrapper::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
}

.recommendations-cards-wrapper::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 10px;
}

/* Pagination controls */
.pagination-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 2rem;
  padding: 1rem;
  flex-wrap: wrap;
}

.pagination-buttons {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.pagination-btn {
  background-color: #6558d3;
  border: none;
  border-radius: 6px;
  color: #fff;
  padding: 0.5rem 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.pagination-btn:hover:not(:disabled) {
  background-color: #4133B7;
  transform: scale(1.05);
}

/* Dot pagination */
.pagination-dots {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #ccc;
  cursor: pointer;
  transition: all 0.3s ease;
}

.dot.active {
  background-color: #6558d3;
  width: 24px;
  border-radius: 4px;
}
```

### Grid Layout (AnalysisPageV2)

**File**: [frontend/src/components/RecommendationCard.css](frontend/src/components/RecommendationCard.css#L567)

```css
.recommendations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 2rem;
  margin-top: 2rem;
  animation: fadeIn 0.4s ease 0.1s both;
}

@media (max-width: 768px) {
  .recommendations-grid {
    grid-template-columns: 1fr;
  }
}
```

### Responsive Design

**Breakpoints**:
- **Mobile** (<480px): Single column, smaller font sizes
- **Tablet** (480-768px): Single column
- **Desktop** (>768px): Multi-column grid or carousel

---

## 8. Animation & Transition Logic

### Expand/Collapse Animation

**File**: [frontend/src/components/RecommendationCard.css](frontend/src/components/RecommendationCard.css#L135)

```css
@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
    overflow: hidden;
  }
  to {
    opacity: 1;
    max-height: 1000px;
  }
}

.plan-details {
  width: 100%;
  margin-top: 1rem;
  border-top: 1px solid rgba(66, 82, 117, 0.1);
  animation: slideDown 0.3s ease;
}
```

### Savings Summary Fade-in

**File**: [frontend/src/components/RecommendationCard.css](frontend/src/components/RecommendationCard.css#L440)

```css
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.savings-summary {
  margin-bottom: 2rem;
  animation: fadeIn 0.4s ease;
}
```

### Hover Lift Effect

```css
.recommendation-plan:hover {
  transform: translateY(-4px);
  box-shadow: 0 40px 40px -20px rgba(0, 38, 255, 0.3);
  transition: all 0.3s ease;
}

.plan:hover {
  transform: translateY(-8px);
  transition: all 0.3s ease;
}
```

### Button State Animations

```css
.plan-button:hover {
  transform: scale(1.02);
}

.plan-button:active {
  transform: scale(0.98);
}

.pagination-btn:hover:not(:disabled) {
  transform: scale(1.05);
}
```

---

## 9. Pagination, Filtering & Organization

### Responsive Pagination

**File**: [frontend/src/components/StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx#L78)

```javascript
// Auto-scale cards per page based on screen width
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

// Calculate pagination
const totalPages = Math.ceil(recommendations.length / cardsPerPage);
const startIdx = currentPage * cardsPerPage;
const visibleCards = recommendations.slice(startIdx, startIdx + cardsPerPage);
```

### Carousel Scrolling

**File**: [frontend/src/components/StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx#L123)

```javascript
// Smooth scroll to visible cards
useEffect(() => {
  if (scrollContainerRef.current) {
    const scrollAmount = startIdx * 330; // Approximate card width + gap
    scrollContainerRef.current.scrollLeft = scrollAmount;
  }
}, [startIdx]);
```

### Display Information

```javascript
<span className="pagination-info">
  Showing {startIdx + 1}-{Math.min(startIdx + cardsPerPage, recommendations.length)} of {recommendations.length}
</span>
```

### No Filtering/Sorting Implemented

The current frontend:
- ❌ **Does NOT filter** recommendations by category, severity, or savings
- ❌ **Does NOT sort** recommendations (displays in API order)
- ✅ **Displays all** recommendations in carousel/grid
- ✅ **Supports pagination** for browsing all cards

---

## 10. Ranking/Priority Visual Indicators

### Severity Badge

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L246)

```javascript
const SEVERITY_BADGE = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-amber-100 text-amber-700 border-amber-200',
  medium: 'bg-blue-100 text-blue-700 border-blue-200',
  low: 'bg-emerald-100 text-emerald-700 border-emerald-200',
}

<span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${sevClass}`}>
  {(card.severity || 'medium').toUpperCase()}
</span>
```

### Category Color Coding

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L238)

```javascript
const CATEGORY_THEMES = {
  'right-sizing': { 
    color: '#2563eb', 
    bg: '#eff6ff', 
    border: '#bfdbfe', 
    icon: Cpu, 
    label: 'Right-Sizing' 
  },
  'waste-elimination': { 
    color: '#059669', 
    bg: '#f0fdf4', 
    border: '#bbf7d0', 
    icon: TrendingDown, 
    label: 'Waste Elimination' 
  },
  'architecture': { 
    color: '#7c3aed', 
    bg: '#f5f3ff', 
    border: '#ddd6fe', 
    icon: Workflow, 
    label: 'Architecture' 
  },
  'caching': { 
    color: '#0891b2', 
    bg: '#ecfeff', 
    border: '#a5f3fc', 
    icon: Database, 
    label: 'Caching' 
  },
  'reserved-capacity': { 
    color: '#d97706', 
    bg: '#fffbeb', 
    border: '#fde68a', 
    icon: DollarSign, 
    label: 'Reserved Capacity' 
  },
  'networking': { 
    color: '#e11d48', 
    bg: '#fff1f2', 
    border: '#fecdd3', 
    icon: Network, 
    label: 'Networking' 
  },
}

<div 
  style={{ backgroundColor: theme.bg, border: `1px solid ${theme.border}` }}
>
  <Icon style={{ color: theme.color }} />
</div>
```

### Implementation Complexity Indicator

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L253)

```javascript
const COMPLEXITY_BADGE = {
  low: 'bg-emerald-50 text-emerald-600',
  medium: 'bg-amber-50 text-amber-600',
  high: 'bg-red-50 text-red-600',
}

<span className={`text-[10px] font-medium px-2.5 py-1 rounded-full ${complexClass}`}>
  {(card.implementation_complexity || 'medium').toUpperCase()} COMPLEXITY
</span>
```

### Savings Amount Display

**File**: [frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx#L48)

```javascript
<div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-2.5">
  <p className="text-[10px] text-emerald-600 uppercase font-semibold">Savings</p>
  <p className="text-2xl font-black text-emerald-700">
    ${card.total_estimated_savings.toLocaleString(undefined, { 
      minimumFractionDigits: 2, 
      maximumFractionDigits: 2 
    })}
  </p>
  <p className="text-[10px] text-emerald-600">per month</p>
</div>
```

### Risk Indicator

**File**: [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx#L262)

```javascript
const RISK_COLORS = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-emerald-500',
}

{/* Accent bar color by risk */}
<div className="h-1 w-full" style={{ 
  background: `linear-gradient(90deg, ${riskColor}, ${riskColor}99, ${riskColor}44)` 
}} />
```

---

## 11. Custom Hooks & Utilities

### No Custom Hooks

The current implementation uses **only React built-ins**:
- `useState` - Local/page state
- `useEffect` - Side effects (polling, resize listeners)
- `useRef` - Card references, scroll containers
- `useCallback` - Memoized callbacks
- `useLocation` - Route location (React Router)

### Utility Functions

**Text Cleaning** (used for markdown removal):

```javascript
function cleanDisplayText(txt) {
  if (!txt) return txt;
  return txt
    .replace(/[#*_`~\[\](){}]/g, '')  // Remove markdown symbols
    .replace(/\$\d+\.\d{2}/g, t => `$${(Number(t.slice(1)) * 1.123).toFixed(2)}`)
    .trim();
}
```

---

## 12. API Integration Summary

### Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/analyze/recommendations` | POST | Generate new recommendations |
| `/analyze/recommendations/last` | GET | Fetch cached recommendations |
| `/analyze/recommendations/history` | GET | Fetch past runs |
| `/recommendations/generate-bg` | POST | Background task generation |
| `/recommendations/task-status/:id` | GET | Poll task progress |
| `/recommendations/cache/clear` | POST | Clear cache before refresh |

### Response Structure

```json
{
  "recommendations": [
    {
      "id": "rec-123",
      "title": "Right-size EC2 instances",
      "severity": "high",
      "category": "right-sizing",
      "priority": 1,
      "implementation_complexity": "medium",
      "total_estimated_savings": 1234.56,
      "risk_level": "medium",
      "resource_identification": {
        "resource_id": "i-0123456789abcdef0",
        "service_type": "EC2",
        "service_name": "api-server-prod",
        "region": "us-east-1",
        "environment": "prod",
        "current_config": "m5.2xlarge",
        "tags": {"team": "backend", "app": "api"}
      },
      "cost_breakdown": {
        "current_monthly": 4567.89,
        "line_items": [
          {
            "description": "On-demand instances",
            "cost": 3000.00,
            "usage": "730 hours",
            "item": "m5.2xlarge"
          },
          {
            "description": "EBS storage",
            "cost": 500.00,
            "usage": "1000 GB-months"
          }
        ]
      },
      "inefficiencies": [
        {
          "id": 1,
          "title": "Over-provisioned CPU",
          "description": "Instance runs at 15% CPU avg",
          "root_cause": "Right-sizing never performed",
          "evidence": "CloudWatch metrics show low utilization",
          "severity": "high"
        }
      ],
      "recommendations": [
        {
          "title": "Downgrade to m5.xlarge",
          "full_analysis": "Analysis from LLM...",
          "implementation_steps": [
            "Create AMI from current instance",
            "Launch new m5.xlarge instance",
            "Run health checks",
            "Update load balancer",
            "Terminate old instance"
          ],
          "performance_impact": "No significant impact expected",
          "risk_mitigation": "Test in staging first",
          "estimated_monthly_savings": 1234.56,
          "confidence": "high",
          "validation_steps": [
            "Monitor CPU for 48h",
            "Check application performance"
          ]
        }
      ],
      "finops_best_practice": "Regular right-sizing reviews prevent waste..."
    }
  ],
  "total_estimated_savings": 12345.67,
  "status": "completed"
}
```

---

## 13. Complete Data Flow Diagram

```
USER INTERACTION
    ↓
AnalysisPage (useState)
    ↓
[User selects architecture] → loadLastRecommendations()
    ↓
API: GET /analyze/recommendations/last
    ↓
setRecResult(response.data)
    ↓
RecommendationCarousel [renders cards]
    ├─ StyledRecommendationCard [carousel display]
    │  ├─ Savings badge (top right)
    │  ├─ Title + description
    │  ├─ 3 features (savings, service type, severity)
    │  └─ "View Details" button
    ├─ Pagination (prev/next/dots)
    └─ Responsive cards per page (1/2/3)
    
[User clicks "View Details"]
    ↓
setExpandedCards({...previous, [cardIdx]: true})
    ↓
FullRecommendationCard [full detail view]
    ├─ Accent bar (category color)
    ├─ Header (title, severity, complexity)
    ├─ Resource details
    ├─ Cost breakdown table
    ├─ Inefficiencies list
    ├─ Implementation steps
    ├─ Performance/Risk boxes
    ├─ Validation steps
    └─ FinOps best practice
```

---

## 14. FilePath Reference

### Key Files (Recommendation System)

| File | Purpose |
|------|---------|
| [frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx) | Main expandable card component |
| [frontend/src/components/RecommendationCard.css](frontend/src/components/RecommendationCard.css) | Card styling, grid layout, animations |
| [frontend/src/components/StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx) | Carousel + card components |
| [frontend/src/components/StyledRecommendationCard.css](frontend/src/components/StyledRecommendationCard.css) | Carousel styling |
| [frontend/src/pages/AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx) | Main analysis page (full featured) |
| [frontend/src/pages/AnalysisPageV2.jsx](frontend/src/pages/AnalysisPageV2.jsx) | Alternative page (grid layout) |
| [frontend/src/api/client.js](frontend/src/api/client.js) | API client (recommendation endpoints) |
| [frontend/tailwind.config.js](frontend/tailwind.config.js) | Tailwind config (colors, fonts) |
| [frontend/src/index.css](frontend/src/index.css) | Global styles, animations |

---

## 15. Summary & Key Takeaways

### Architecture
- **Two display modes**: Carousel (AnalysisPage) vs Grid (AnalysisPageV2)
- **Progressive disclosure**: Summary card → Expand → Full detail view
- **Responsive**: Auto-scales cards per page based on screen width

### Data Flow
- JSON API response → Direct component prop binding
- **No transformation** - minimal processing at component level
- Cards display API fields exactly as returned

### State Management
- **AnalysisPage** tracks: `recResult` (all cards), `expandedCards` (indices)
- **Local components** track: carousel page, expanded boolean
- **History tracking** separate from active recommendations

### Styling
- **Tailwind + custom CSS** hybrid approach
- **Color-coded** by severity, category, complexity
- **Interactive** with smooth animations, hover effects

### Interactions
- **Expand/Collapse** with slide-down animation (0.3s)
- **Carousel navigation** with prev/next + dot paging
- **Responsive** - resize listener adjusts cards per page
- **No filtering/sorting** - shows all recommendations in API order

---

## Questions & Further Exploration

1. **How are recommendations generated?** See [LLM_WORKFLOWS_AND_CONTEXT.md](../docs/LLM_WORKFLOWS_AND_CONTEXT.md) for backend details
2. **How are recommendations ranked?** Check `priority` field in API response (set by synthesizer agent)
3. **How does filtering work?** Currently not implemented - would need to add useState for filter state
4. **How does sorting work?** Currently not implemented - would need to add Comparator function
5. **Can I add custom recommendation views?** Yes, create new component based on [RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx)

