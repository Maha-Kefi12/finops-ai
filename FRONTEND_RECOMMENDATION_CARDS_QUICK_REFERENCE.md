# Frontend Recommendation Cards - Quick Reference & Code Snippets

## Quick Links to Key Code

### Component Files
- **Main Card Component**: [RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx) (287 lines)
- **Carousel Card**: [StyledRecommendationCard.jsx](frontend/src/components/StyledRecommendationCard.jsx) (180+ lines)
- **Main Page**: [AnalysisPage.jsx](frontend/src/pages/AnalysisPage.jsx) (1700+ lines)
- **Alternative Page**: [AnalysisPageV2.jsx](frontend/src/pages/AnalysisPageV2.jsx) (230+ lines)
- **Card Styling**: [RecommendationCard.css](frontend/src/components/RecommendationCard.css) (600+ lines)
- **Carousel Styling**: [StyledRecommendationCard.css](frontend/src/components/StyledRecommendationCard.css) (300+ lines)

### API Client
- **API Functions**: [client.js](frontend/src/api/client.js) - Recommendation endpoints

---

## Copy-Paste Code Snippets

### 1. Fetch Recommendations

```javascript
import { generateRecommendations, getLastRecommendations } from '../api/client';

// Method 1: Fetch latest (cached if available)
async function loadRecommendations() {
  try {
    const res = await getLastRecommendations('arch-123', null);
    setRecResult(res.data);
    console.log('Recommendations:', res.data.recommendations);
  } catch (error) {
    console.error('Failed:', error);
  }
}

// Method 2: Generate fresh (non-cached)
async function generateFresh() {
  try {
    setRecLoading(true);
    const res = await generateRecommendations('arch-123', null);
    setRecResult(res.data);
  } catch (error) {
    setRecError(error.message);
  } finally {
    setRecLoading(false);
  }
}
```

### 2. Display Summary Banner

```javascript
// From <SavingsSummary /> component
<div className="savings-card main">
  <h2 className="savings-title">💰 Total Potential Savings</h2>
  
  <div className="savings-amount-large">
    ${totalMonthly.toFixed(0)}
    <span className="savings-period">/month</span>
  </div>
  
  <div className="savings-annual">
    ${(totalMonthly * 12).toFixed(0)} per year
  </div>
  
  <div className="savings-meta">
    <span className="meta-item">
      {recommendationCount} recommendations
    </span>
    <span className={`meta-status ${status}`}>
      {status === 'generating' && '⏳ Analyzing...'}
      {status === 'completed' && '✓ Ready'}
      {status === 'idle' && '○ Idle'}
    </span>
  </div>
</div>
```

### 3. Render Carousel

```javascript
import { RecommendationCarousel } from '../components/StyledRecommendationCard';

<RecommendationCarousel 
  recommendations={recResult.recommendations || []}
  onViewDetails={(rec) => {
    // Find index and expand
    const recIdx = recResult.recommendations.findIndex(r => r === rec);
    if (recIdx >= 0) {
      setExpandedCards(prev => ({ ...prev, [recIdx]: true }));
      // Scroll to expanded card
      setTimeout(() => {
        document.querySelector(`[data-rec-id="${recIdx}"]`)?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest'
        });
      }, 100);
    }
  }}
/>
```

### 4. Render Grid Instead

```javascript
import { RecommendationCard } from '../components/RecommendationCard';

<div className="recommendations-grid">
  {(recResult.recommendations || []).map((rec, idx) => (
    <RecommendationCard
      key={rec.id || idx}
      recommendation={rec}
      totalSavingsPerMonth={recResult.total_estimated_savings}
      onExpand={(card) => console.log('Expanded:', card)}
    />
  ))}
</div>
```

### 5. Expand/Collapse Card

```javascript
const [showDetails, setShowDetails] = useState(false);

const handleExpand = () => {
  setShowDetails(!showDetails);
};

// Button
<button className="plan-button" onClick={handleExpand}>
  {showDetails ? 'Hide Details' : 'View Details'} →
</button>

// Conditional content
{showDetails && (
  <div className="plan-details" style={{ animation: 'slideDown 0.3s ease' }}>
    {/* Expanded content here */}
  </div>
)}
```

### 6. Handle Pagination

```javascript
const [currentPage, setCurrentPage] = useState(0);
const [cardsPerPage, setCardsPerPage] = useState(3);

const totalPages = Math.ceil(recommendations.length / cardsPerPage);
const startIdx = currentPage * cardsPerPage;
const visibleCards = recommendations.slice(startIdx, startIdx + cardsPerPage);

const handlePrevPage = () => {
  setCurrentPage(prev => (prev > 0 ? prev - 1 : totalPages - 1));
};

const handleNextPage = () => {
  setCurrentPage(prev => (prev < totalPages - 1 ? prev + 1 : 0));
};

// Responsive cards per page
useEffect(() => {
  const handleResize = () => {
    if (window.innerWidth < 768) setCardsPerPage(1);
    else if (window.innerWidth < 1200) setCardsPerPage(2);
    else setCardsPerPage(3);
  };
  handleResize();
  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, []);
```

### 7. Display Severity Badge

```javascript
const severityMap = {
  critical: { bg: '#FFE5E5', color: '#ED4B4B' },
  high: { bg: '#FFE8D6', color: '#F66B35' },
  medium: { bg: '#FFF8DC', color: '#FFC045' },
  low: { bg: '#E8F5E9', color: '#4CAF50' },
};

const sev = severityMap[recommendation.severity] || severityMap.medium;

<span 
  className="badge severity" 
  style={{ 
    backgroundColor: sev.bg,
    color: sev.color,
    fontSize: '0.75rem'
  }}
>
  {recommendation.severity.toUpperCase()}
</span>
```

### 8. Display Category Color

```javascript
const categoryThemes = {
  'right-sizing': { color: '#2563eb', bg: '#eff6ff' },
  'waste-elimination': { color: '#059669', bg: '#f0fdf4' },
  'architecture': { color: '#7c3aed', bg: '#f5f3ff' },
  'caching': { color: '#0891b2', bg: '#ecfeff' },
  'reserved-capacity': { color: '#d97706', bg: '#fffbeb' },
  'networking': { color: '#e11d48', bg: '#fff1f2' },
};

const theme = categoryThemes[rec.category] || categoryThemes['right-sizing'];

<div style={{ 
  backgroundColor: theme.bg,
  borderLeft: `4px solid ${theme.color}`,
  padding: '1rem',
  borderRadius: '8px'
}}>
  {/* Content here */}
</div>
```

### 9. Display Cost Breakdown Table

```javascript
{recommendation.cost_breakdown?.line_items?.length > 0 && (
  <div className="detail-section">
    <h4>Cost Breakdown</h4>
    <table>
      <thead>
        <tr>
          <th>Description</th>
          <th>Usage</th>
          <th>Cost</th>
        </tr>
      </thead>
      <tbody>
        {recommendation.cost_breakdown.line_items.map((item, idx) => (
          <tr key={idx}>
            <td>{item.description}</td>
            <td>{item.usage}</td>
            <td>${item.cost?.toFixed(2) || '0.00'}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan="2">Total Monthly</td>
          <td>${recommendation.cost_breakdown.current_monthly?.toFixed(2) || '0.00'}</td>
        </tr>
      </tfoot>
    </table>
  </div>
)}
```

### 10. Display Implementation Steps

```javascript
{recommendation.recommendations?.[0]?.implementation_steps?.length > 0 && (
  <div className="detail-section">
    <h4>Action Plan</h4>
    <ol>
      {recommendation.recommendations[0].implementation_steps.map((step, idx) => (
        <li key={idx}>
          <strong>Step {idx + 1}:</strong> {step}
        </li>
      ))}
    </ol>
  </div>
)}
```

### 11. Handle Refresh

```javascript
const handleRefresh = async () => {
  try {
    // Clear cache
    await fetch('/api/recommendations/cache/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        architecture_id: architectureId,
        architecture_file: architectureFile,
      }),
    });
    
    // Generate fresh
    setRecLoading(true);
    const res = await generateRecommendations(architectureId, architectureFile);
    setRecResult(res.data);
  } catch (error) {
    console.error('Refresh failed:', error);
  } finally {
    setRecLoading(false);
  }
};

<button onClick={handleRefresh} disabled={recLoading}>
  🔄 Refresh Analysis
</button>
```

### 12. Load History

```javascript
async function loadHistory() {
  try {
    const res = await fetch(
      `/api/recommendations/history?architecture_id=${archId}&limit=10`
    );
    const data = await res.json();
    setRecHistory(data.history || []);
  } catch (error) {
    console.error('Failed to load history:', error);
  }
}

{recHistory.length > 0 && (
  <div className="history-container">
    <h3>📋 Recommendation History</h3>
    {recHistory.map((item, idx) => (
      <div key={idx} className="history-item">
        <div className="history-header">
          <span className="history-date">
            {new Date(item.created_at).toLocaleDateString()}
          </span>
          <span className={`history-status ${item.status}`}>
            {item.status === 'completed' ? '✓ Completed' : '✗ Failed'}
          </span>
        </div>
        <div className="history-meta">
          <span>{item.card_count} recommendations</span>
          <span>💰 ${item.total_estimated_savings?.toFixed(0) || 0}/mo</span>
          <span>{item.generation_time_ms}ms</span>
        </div>
      </div>
    ))}
  </div>
)}
```

---

## Common Patterns

### Pattern 1: Conditional Rendering

```javascript
// Show card if data exists
{recommendation.title && (
  <h3 className="plan-title">
    {recommendation.title}
  </h3>
)}

// Show section only if has data
{recommendation.inefficiencies?.length > 0 && (
  <div className="detail-section">
    {/* content */}
  </div>
)}
```

### Pattern 2: Safe Number Formatting

```javascript
// Format currency
${(number || 0).toFixed(2)}

// Format with thousand separators
${(number || 0).toLocaleString(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})}

// Percentage
{(number * 100).toFixed(1)}%
```

### Pattern 3: Ternary for Badge Styling

```javascript
className={`badge ${rec.severity === 'critical' ? 'critical' : 'normal'}`}

// Or with object map
const classMap = { critical: 'red', high: 'orange', medium: 'yellow', low: 'green' };
className={`badge ${classMap[rec.severity] || 'blue'}`}
```

### Pattern 4: Array Safe Access

```javascript
// Safe access to nested property
recommendation.resource_identification?.service_type || 'N/A'

// Safe array access
recommendation.recommendations?.[0]?.implementation_steps || []

// Optional chaining with map
recommendation.cost_breakdown?.line_items?.map((item) => {...})
```

### Pattern 5: State Update Patterns

```javascript
// Toggle boolean
setShowDetails(!showDetails);

// Update object at index
setExpandedCards(prev => ({...prev, [idx]: true}));

// Array update
setHistory(prev => [newItem, ...prev]);

// Clear state
setExpandedCards({});
```

---

## CSS Quick Snippets

### Severity Button Styling

```css
/* Reusable severity badge */
.badge.severity {
  padding: 0.375em 0.75em;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.severity.critical {
  background-color: #FFE5E5;
  color: #ED4B4B;
}

.badge.severity.high {
  background-color: #FFE8D6;
  color: #F66B35;
}
```

### Card Hover Effect

```css
.card {
  transition: all 0.3s ease;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 40px 40px -20px rgba(0, 38, 255, 0.3);
}
```

### Expand Animation

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

.expanded-details {
  animation: slideDown 0.3s ease;
}
```

### Responsive Grid

```css
/* Flexible grid */
.recommendations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 2rem;
}

@media (max-width: 768px) {
  .recommendations-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
}
```

### Horizontal Carousel

```css
.carousel-container {
  display: flex;
  gap: 1.5rem;
  overflow-x: auto;
  scroll-behavior: smooth;
  scroll-snap-type: x mandatory;
}

.carousel-container > * {
  flex: 0 0 auto;
  scroll-snap-align: start;
}

/* Custom scrollbar */
.carousel-container::-webkit-scrollbar {
  height: 6px;
}

.carousel-container::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 10px;
}
```

---

## Testing Code

### Test: Fetch Recommendations

```javascript
// In your test file
import { generateRecommendations } from '../api/client';

test('should fetch recommendations', async () => {
  const response = await generateRecommendations('arch-123');
  expect(response.data.recommendations).toBeDefined();
  expect(Array.isArray(response.data.recommendations)).toBe(true);
  expect(response.data.total_estimated_savings).toBeGreaterThan(0);
});
```

### Test: Expand Card

```javascript
import { render, screen, fireEvent } from '@testing-library/react';
import { RecommendationCard } from '../components/RecommendationCard';

test('should expand card on button click', () => {
  const mockRec = {
    title: 'Test',
    severity: 'high',
    total_estimated_savings: 100,
    resource_identification: { resource_id: 'test' },
    cost_breakdown: {},
    inefficiencies: [],
    recommendations: [],
  };

  render(<RecommendationCard recommendation={mockRec} />);
  
  const button = screen.getByRole('button', { name: /view details/i });
  fireEvent.click(button);
  
  // Details should be visible
  expect(screen.getByText(/resource details/i)).toBeInTheDocument();
});
```

### Test: Pagination

```javascript
test('should navigate pagination', () => {
  const recommendations = Array(10).fill({...mockRec});
  
  const { rerender } = render(
    <RecommendationCarousel recommendations={recommendations} />
  );
  
  // Get next button
  const nextBtn = screen.getByRole('button', { name: /next/i });
  fireEvent.click(nextBtn);
  
  // Check page indicator updated
  expect(screen.getByText(/2 \/ \d+/)).toBeInTheDocument();
});
```

---

## Debugging Tips

### 1. Console Logging

```javascript
// Log when state updates
useEffect(() => {
  console.log('Recommendations updated:', recResult);
}, [recResult]);

// Log in click handlers
const handleExpand = (rec) => {
  console.log('Expanded card:', rec.id, rec.title);
  setShowDetails(!showDetails);
};
```

### 2. React DevTools

- Install React DevTools browser extension
- Click on components in tree
- See props/state in right panel
- Edit state values in real-time

### 3. Network Debugger

```javascript
// Add network logging
const api = axios.create({baseURL: '/api'});

api.interceptors.request.use(config => {
  console.log('API Request:', config);
  return config;
});

api.interceptors.response.use(response => {
  console.log('API Response:', response.data);
  return response;
}, error => {
  console.error('API Error:', error);
  return Promise.reject(error);
});
```

### 4. Check Props in Console

```javascript
function RecommendationCard(props) {
  useEffect(() => {
    console.table(props.recommendation);
  }, [props.recommendation]);
  
  return <div>...</div>;
}
```

---

## Performance Optimization Tips

### 1. Memoize Components

```javascript
import { memo } from 'react';

// Before: Re-renders on every parent update
function StyledCard({ recommendation, onViewDetails }) {
  return <div>...</div>;
}

// After: Only re-renders if props change
export const StyledCard = memo(function StyledCard({ recommendation, onViewDetails }) {
  return <div>...</div>;
});
```

### 2. Use useCallback for Handlers

```javascript
// Before: New function created on every render
<RecommendationCarousel onViewDetails={(rec) => handleView(rec)} />

// After: Function memoized
const handleViewDetails = useCallback((rec) => {
  const recIdx = recommendations.findIndex(r => r === rec);
  setExpandedCards(prev => ({...prev, [recIdx]: true}));
}, [recommendations]);

<RecommendationCarousel onViewDetails={handleViewDetails} />
```

### 3. Virtual List for 100+ Cards

```javascript
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={recommendations.length}
  itemSize={350}
  width="100%"
>
  {({ index, style }) => (
    <div style={style}>
      <RecommendationCard recommendation={recommendations[index]} />
    </div>
  )}
</FixedSizeList>
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Cards not displaying | Check `recResult.recommendations` is array, not null |
| Expand button not working | Verify `onClick={handleExpand}` bound correctly |
| Styling not applied | Check CSS file imported, no typos in className |
| Pagination stuck | Check `totalPages` > 0, not dividing by zero |
| API timeout | Increase timeout or check backend logs |
| Cards lag on scroll | Use React.memo on cards, consider virtual list |
| Styles overriding | Check CSS specificity, use !important as last resort |
| History not loading | Verify `/api/recommendations/history` endpoint exists |

---

## Resources

- [React Hooks Docs](https://react.dev/reference/react)
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [Axios Docs](https://axios-http.com/)
- [React Router Docs](https://reactrouter.com/)
- [MDN CSS Animations](https://developer.mozilla.org/en-US/docs/Web/CSS/animation)

