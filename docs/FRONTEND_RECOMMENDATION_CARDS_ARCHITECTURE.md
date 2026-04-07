# FinOps AI Frontend - Recommendation Card Architecture Diagram

## Component Hierarchy

```
App (Router)
│
└── AnalysisPage ✨ MAIN PAGE FOR RECOMMENDATIONS
    │
    ├── STATE:
    │   ├── recResult: { recommendations: [...], total_estimated_savings: 0 }
    │   ├── expandedCards: { 0: true, 2: false, ... }
    │   ├── recLoading: boolean
    │   └── recHistory: [{...}, {...}]
    │
    ├── SavingsSummary (Banner at top)
    │   ├── Total $ savings/month
    │   ├── Total $/year
    │   └── Status indicator (generating | completed | idle)
    │
    ├── Controls (Buttons)
    │   ├── Refresh (clears cache, regenerates)
    │   ├── History (show past runs)
    │   └── Task Progress (if generating)
    │
    ├── RecommendationCarousel
    │   │
    │   ├── [Page 1] StyledRecommendationCard
    │   │   ├── Savings badge ($$$, top right)
    │   │   ├── Title + service type
    │   │   ├── Features list (3 max)
    │   │   │   ├── Save $X/month
    │   │   │   ├── Service type (EC2, RDS, etc)
    │   │   │   └── Severity (CRITICAL, HIGH, etc)
    │   │   └── [View Details] button
    │   │
    │   ├── [Page 2] StyledRecommendationCard
    │   └── [Page 3] StyledRecommendationCard
    │
    ├── Pagination Controls
    │   ├── [← Prev] [1 / 5] [Next →]
    │   ├── Dot indicators (● ● ● ● ●)
    │   └── "Showing X-Y of Z"
    │
    ├── FullRecommendationCard [Expanded Details] ✨ DETAILED VIEW
    │   │
    │   ├── Accent bar (category color)
    │   │   └── Color by: right-sizing | waste | architecture | caching | reserved | networking
    │   │
    │   ├── Header Row
    │   │   ├── Icon (category themed)
    │   │   ├── Title
    │   │   ├── Badges
    │   │   │   ├── Severity (critical|high|medium|low)
    │   │   │   ├── Category (Right-Sizing, etc)
    │   │   │   └── Complexity (LOW|MEDIUM|HIGH)
    │   │   ├── Resource info (service, region)
    │   │   └── Savings box (right side)
    │   │       ├── $1234.56
    │   │       └── per month
    │   │
    │   ├── Resource Details Section
    │   │   ├── Current config (instance type, etc)
    │   │   └── Tags (team: backend, env: prod)
    │   │
    │   ├── CUR Cost Breakdown (Table)
    │   │   ├── Line Item | Usage | Cost
    │   │   ├── On-demand instances | 730h | $3000
    │   │   ├── EBS storage | 1000GB | $500
    │   │   └── Total Monthly: $3500
    │   │
    │   ├── Inefficiencies Section
    │   │   ├── [BADGE] Issue #1: Over-provisioned CPU
    │   │   │   ├── Description
    │   │   │   └── Evidence
    │   │   └── [BADGE] Issue #2: ...
    │   │
    │   ├── Implementation Steps (Numbered)
    │   │   ├── 1️⃣ Create AMI from current
    │   │   ├── 2️⃣ Launch new instance
    │   │   ├── 3️⃣ Run health checks
    │   │   ├── 4️⃣ Update load balancer
    │   │   └── 5️⃣ Terminate old instance
    │   │
    │   ├── Performance Impact + Risk Mitigation
    │   │   ├── [Blue Box] Performance Impact: No significant change expected
    │   │   └── [Amber Box] Risk Mitigation: Test in staging first
    │   │
    │   ├── Validation Steps (Checkmarks)
    │   │   ├── ✓ Monitor CPU utilization for 48h
    │   │   └── ✓ Check application response times
    │   │
    │   ├── FinOps Best Practice
    │   │   └── [Green Box] "Right-sizing through Reserved Instances..."
    │   │
    │   └── Footer
    │       ├── Priority #2
    │       └── Risk: medium
    │
    └── RecommendationHistory (Optional)
        ├── Past run 1 (2024-01-15 10:30)
        │   ├── ✓ Completed
        │   ├── 5 recommendations
        │   └── $2345.67/mo
        └── Past run 2 (2024-01-14 09:15)
            ├── ✓ Completed
            ├── 7 recommendations
            └── $3456.78/mo


alt AnalysisPageV2
│
├── SavingsSummary (Banner)
├── Controls
└── Recommendations Grid (responsive)
    ├── Card 1 (RecommendationCard)
    ├── Card 2 (RecommendationCard)
    ├── Card 3 (RecommendationCard)
    └── Card 4 (RecommendationCard)
```

---

## Data Flow: API → UI

```
┌─────────────────────────────┐
│  Backend API Response       │
│  (/api/analyze/recommendations)
└──────────────┬──────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ {                        │
    │  recommendations: [      │
    │    {                     │
    │      title: "...",       │
    │      severity: "high",   │
    │      category: "...",    │
    │      total_estimated...: │
    │      resource_...: {...},│
    │      cost_breakdown:{...}│
    │      ...                 │
    │    },                    │
    │    {...},                │
    │    {...}                 │
    │  ],                      │
    │  total_estimated...      │
    │ }                        │
    └──────────────┬───────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │  AnalysisPage.jsx            │
    │  const [recResult] = useState │
    │  setRecResult(data)          │
    └──────────────┬───────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
    RecommendationCarousel  SavingsSummary
    (recResult.recommendations)
         │
    ┌────┴────────────────────┐
    │                         │
    ▼                         ▼
 Map & Render        Pagination State
 StyledCards         (currentPage, cardsPerPage)
    │
    ├─ Card 1: title, savings, features
    ├─ Card 2: ...
    └─ Card 3: ...
    
    [User clicks "View Details"]
         │
         ▼
    setExpandedCards({...prev, [0]: true})
         │
         ▼
    FullRecommendationCard expands
    (renders all nested fields)
```

---

## State Management Flow

```
AnalysisPage Component State:
│
├─ recResult: null → {recommendations, total_estimated_savings}
│  │  ▲
│  │  │ Updates from API
│  │  └─ setRecResult(response.data)
│  │
│  └─ Read by:
│     ├─ RecommendationCarousel (map over recommendations)
│     ├─ SavingsSummary (display total_estimated_savings)
│     └─ FullRecommendationCard (expanded details)
│
├─ expandedCards: {} → {0: true, 2: true, ...}
│  │  ▲
│  │  │ Updates on "View Details" click
│  │  └─ setExpandedCards(prev => ({...prev, [idx]: true}))
│  │
│  └─ Read by:
│     ├─ StyledRecommendationCard (show/hide button state)
│     └─ FullRecommendationCard (render conditionally)
│
├─ recLoading: false → true → false
│  │  ▲
│  │  │ During API call
│  │  └─ setRecLoading(true|false)
│  │
│  └─ Read by:
│     └─ Display loading spinner
│
├─ recHistory: [] → [{...}, {...}]
│  │  ▲
│  │  │ Fetched from history endpoint
│  │  └─ setRecHistory(data.history)
│  │
│  └─ Read by:
│     └─ RecommendationHistory (show past runs)
│
└─ selectedHistorySnapshot: null → {...}
   │  ▲
   │  │ User clicks history item
   │  └─ setSelectedHistorySnapshot(historyItem)
   │
   └─ Read by:
      └─ Display if user wants to show past results
```

---

## Styling Cascade

```
Tailwind Config (tailwind.config.js)
├─ Colors
│  ├─ brand-600: #4f46e5 (primary purple)
│  └─ Custom: surface colors, animations
│
├─ Font
│  └─ Inter 300-900
│
└─ Animations
   ├─ fadeInUp
   ├─ shimmer
   └─ spin

                  ▼

Global Styles (index.css)
├─ @import tailwind directives
├─ Base styles (@layer base)
├─ Component styles (@layer components)
└─ Custom animations

                  ▼

Component CSS Files
├─ RecommendationCard.css
│  ├─ .recommendation-plan (card container)
│  ├─ .plan-inner (content area)
│  ├─ .plan-savings (badge)
│  ├─ .plan-details (expandable section)
│  ├─ .recommendations-grid (layout)
│  └─ @media queries (responsive)
│
└─ StyledRecommendationCard.css
   ├─ .plan (carousel card)
   ├─ .recommendations-cards-wrapper (carousel container)
   ├─ .pagination-controls (buttons + dots)
   └─ @media queries

                  ▼

JSX Component (renders with className)
└─ <div className="recommendation-plan">
   └─ Matches .recommendation-plan from CSS
```

---

## Color Coding System

```
SEVERITY LEVELS (Badge colors):
├─ critical → bg-red-100, text-red-700
├─ high → bg-amber-100, text-amber-700
├─ medium → bg-blue-100, text-blue-700
└─ low → bg-emerald-100, text-emerald-700

CATEGORY THEMES (Accent bar + icon):
├─ right-sizing → #2563eb (blue)
├─ waste-elimination → #059669 (green)
├─ architecture → #7c3aed (purple)
├─ caching → #0891b2 (cyan)
├─ reserved-capacity → #d97706 (amber)
└─ networking → #e11d48 (red)

COMPLEXITY LEVELS (Badge colors):
├─ low → bg-emerald-50, text-emerald-600
├─ medium → bg-amber-50, text-amber-600
└─ high → bg-red-50, text-red-600

SAVINGS DISPLAY (Always):
└─ bg-emerald-50, text-emerald-700, font-black
```

---

## Responsive Breakpoints

```
Desktop (>1200px)
├─ Cards per page: 3
├─ Card width: 300-320px
├─ Grid columns: repeat(auto-fill, minmax(380px, 1fr))
└─ Pagination: prev [1/3] next + dots

Tablet (768px - 1200px)
├─ Cards per page: 2
├─ Single column grid
└─ Pagination: prev [1/2] next + dots

Mobile (<768px)
├─ Cards per page: 1
├─ Single column grid
├─ Font sizes: reduced
└─ Pagination: prev [1/5] next + dots
```

---

## Interaction State Diagram

```
┌─────────────────────────┐
│   IDLE STATE            │
│  (showDetails = false)  │
├─────────────────────────┤
│ Display summary:        │
│ - Savings amount        │
│ - Title (truncated)     │
│ - Service type          │
│ - [View Details] btn    │
└────────────┬────────────┘
             │ User clicks [View Details]
             ▼
┌─────────────────────────┐
│  EXPANDING              │
│  (Animation 0.3s)       │
├─────────────────────────┤
│ Animate: slideDown      │
│ height: 0 → 1000px      │
│ opacity: 0 → 1          │
└────────────┬────────────┘
             │ Animation complete
             ▼
┌─────────────────────────────┐
│  EXPANDED STATE             │
│  (showDetails = true)       │
├─────────────────────────────┤
│ Display full details:       │
│ - Resource details section  │
│ - Cost breakdown table      │
│ - Inefficiencies list       │
│ - Implementation steps      │
│ - Performance/Risk boxes    │
│ - Validation steps          │
│ - FinOps best practice      │
│ - [Hide Details] button     │
└────────────┬────────────────┘
             │ User clicks [Hide Details]
             ▼
┌─────────────────────────┐
│  COLLAPSING             │
│  (Animation 0.3s)       │
├─────────────────────────┤
│ Animate: slideUp        │
│ height: 1000px → 0      │
│ opacity: 1 → 0          │
└────────────┬────────────┘
             │ Animation complete
             ▼
          [IDLE STATE]
```

---

## Carousel Pagination Logic

```
Initial State:
├─ currentPage = 0
├─ cardsPerPage = 3 (desktop)
├─ totalPages = Math.ceil(10 / 3) = 4
└─ visibleCards = cards[0:3]

User clicks Next:
├─ currentPage = 1
├─ visibleCards = cards[3:6]
└─ scroll smooth to card 3

User clicks Next:
├─ currentPage = 2
├─ visibleCards = cards[6:9]
└─ scroll smooth to card 6

User clicks Next:
├─ currentPage = 3 (last page)
├─ visibleCards = cards[9:10]
└─ scroll smooth to card 9

User clicks Next (wraps around):
├─ currentPage = 0 (loop back)
├─ visibleCards = cards[0:3]
└─ scroll smooth to card 0

User clicks dot[2]:
├─ currentPage = 2
├─ visibleCards = cards[6:9]
└─ scroll smooth to card 6

Screen resize (window < 768px):
├─ cardsPerPage = 1
├─ totalPages = Math.ceil(10 / 1) = 10
├─ currentPage = 0 (reset)
└─ visibleCards = cards[0:1]
```

---

## Feature Implementation Map

```
✅ IMPLEMENTED:
├─ Display cards in carousel + grid
├─ Expand/collapse individual cards
├─ Pagination (prev/next + dots)
├─ Responsive design (1/2/3 cards)
├─ Color coding (severity, category, complexity)
├─ Savings amount display (prominent)
├─ Cost breakdown table
├─ Implementation steps (numbered)
├─ Click to expand full details
├─ History tracking
├─ Smooth animations
├─ Refresh button (clear cache)
└─ Task progress indicator

❌ NOT IMPLEMENTED:
├─ Filter by category/severity
├─ Sort by savings/priority/alphabetical
├─ Search/search-as-you-type
├─ Bulk select recommendations
├─ Copy recommendation details
├─ Export to CSV/JSON
├─ Star/bookmark recommendations
├─ Save custom filters
└─ Dark mode toggle

🚀 POSSIBLE ENHANCEMENTS:
├─ Add filter dropdown (category, severity, savings range)
├─ Add sort dropdown (by savings, priority, alphabetical)
├─ Add search box for title/resource
├─ Add bulk action buttons (implement all, dismiss all)
├─ Add copy button in expanded view
├─ Add export button
├─ Add "save for later" feature
└─ Add custom view templates
```

---

## Props Passing Tree

```
AnalysisPage (root state)
│
├─ recResult ──────────────────► RecommendationCarousel
│   (all recommendations)       │
│                               ├─► StyledRecommendationCard (x3)
│                               │   └─ recommendation prop
│                               │       ├─ title
│                               │       ├─ total_estimated_savings
│                               │       ├─ resource_identification
│                               │       └─ (displays in card)
│                               │
│                               └─ onViewDetails callback
│                                   └─ handleCardClick (logs rec index)
│
├─ expandedCards ───────────────► FullRecommendationCard (conditional)
│   ({0: true, 2: true, ...})   │
│                               └─ isExpanded prop (if index in map)
│
├─ recLoading ──────────────────► SavingsSummary (loading spinner)
│
├─ recResult.total_est... ──────► SavingsSummary
│   (for display)              │
│                               └─ totalMonthly prop
│
└─ recHistory ──────────────────► RecommendationHistory (optional)
   ([...])                      │
                               └─ recommendations prop
                                   └─ map over for history items
```

---

## Performance Considerations

```
Rendering:
├─ Carousel: Only 3 cards in DOM (virtualized)
├─ Expanded: Hidden with CSS (visibility: hidden)
├─ Grid: All cards in DOM (10-15 typically)
└─ Total: ~30-50 DOM nodes on typical page

Re-renders trigger on:
├─ expandedCards state change (card expand/collapse)
├─ currentPage state change (pagination)
├─ recResult state change (new recommendations loaded)
├─ Window resize (responsive recalc)
└─ Layout shift on expand (browser reflow)

Optimizations:
├─ Scroll snap (CSS) for carousel
├─ Smooth scroll behavior
├─ memo() could wrap StyledRecommendationCard (not currently used)
├─ Virtual scroll list could be used for 100+ cards
└─ CSS animations (no JS animation frames)

Potential bottlenecks:
├─ Expanding 10+ cards (lots of DOM additions)
├─ API call timeout (default 600s)
└─ Large recommendation response (>10MB)
```

---

## Related Files & Documentation

- **Backend API**: [docs/api_reference.md](../docs/api_reference.md)
- **LLM Workflows**: [docs/LLM_WORKFLOWS_AND_CONTEXT.md](../docs/LLM_WORKFLOWS_AND_CONTEXT.md)
- **Architecture**: [docs/architecture.md](../docs/architecture.md)
- **Recommendation System**: [docs/RECOMMENDATION_SYSTEM_V2.md](../docs/RECOMMENDATION_SYSTEM_V2.md)
