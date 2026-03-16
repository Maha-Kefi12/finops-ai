# FinOps AI - Recommendation System v2.0

## 🎯 Overview

This document describes the **stylish recommendation cards**, **persistent history**, and **background analysis pipeline** for the FinOps AI system.

---

## ✨ New Features

### 1. **Stylish Recommendation Cards**
- Beautiful plan-based card design (inspired by pricing tables)
- Shows **monthly savings in top-right badge**
- Expandable details on click
- Color-coded severity badges
- Implementation steps, cost breakdown, performance impact
- AWS FinOps best practices reference

**Files:**
- `frontend/src/components/RecommendationCard.jsx` - React components
- `frontend/src/components/RecommendationCard.css` - Styling

**Usage:**
```jsx
<RecommendationCard 
  recommendation={rec} 
  onExpand={(card) => console.log(card)}
/>
```

### 2. **Total Savings Display**
- Shows **overall savings from all recommendations** at the top
- Monthly + Annual breakdown
- Real-time status indicator
- Recommendation count

**Component:**
```jsx
<SavingsSummary
  totalMonthly={1000}
  totalAnnual={12000}
  recommendationCount={15}
  status="completed"
/>
```

### 3. **Recommendation History**
- Click "History" button to view past recommendation runs
- Shows timestamp, status, savings, generation time
- Clickable items for drill-down
- Supports up to 100 entries per architecture
- Fast Redis-backed retrieval

**Component:**
```jsx
<RecommendationHistory
  recommendations={historyList}
  onSelect={(rec) => console.log(rec)}
/>
```

### 4. **Background Analysis Pipeline**
- **Refresh button** triggers background generation
- Progress tracking: 0-100% with stage labels
- UI remains responsive (old recommendations stay visible)
- Results auto-populate when ready
- Powered by Celery + Redis

**Flow:**
```
User clicks "Refresh Analysis"
  ↓
POST /api/recommendations/generate-bg
  ↓
Cache cleared, Celery task queued
  ↓
UI shows progress bar (Graph Analysis → Context Assembly → LLM → Saving)
  ↓
Poll GET /api/recommendations/task-status/{task_id} every 1s
  ↓
Task completes → Results appear in grid
  ↓
Latest result shown at top, older ones in history
```

### 5. **Redis Caching**
- **24-hour cache** of recommendation results
- Instant display on page load if fresh
- History stored up to **90 days** in Redis
- Graceful fallback if Redis unavailable

**Cache Keys:**
- `finops:rec:current:{architecture_id}` - Current recommendations
- `finops:rec:history:{architecture_id}` - Historical runs
- `finops:task:{task_id}` - Background task status

### 6. **Hourly CUR Collection Cron**
- Celery Beat scheduler runs **every hour at :00**
- Collects AWS CUR data automatically
- Parses cost data
- Updates database
- No manual trigger needed

**Cron Expression:** `0 * * * *` (every hour)

**Task:** `src.background.tasks.collect_cur_data`

---

## 🚀 Getting Started

### Setup Redis & Celery

**Option 1: Docker Compose (Recommended)**

```bash
# Use extended docker-compose with all services
docker-compose -f docker-compose.extended.yml up -d

# This will start:
# - PostgreSQL (port 5432)
# - Redis (port 6379)
# - Backend API (port 8000)
# - Celery Worker (background tasks)
# - Celery Beat (scheduled tasks)
# - Frontend (port 5173)
# - Ollama LLM (port 11434, optional)
```

**Option 2: Manual Setup**

```bash
# Start Redis
redis-server

# Install Python dependencies
pip install -r requirements.txt
pip install -r docker/api/requirements-background.txt

# Start the backend
uvicorn src.api.main:app --reload

# Start Celery worker (in another terminal)
celery -A src.background.tasks worker --loglevel=info

# Start Celery Beat (in another terminal)
celery -A src.background.tasks beat --loglevel=info
```

### Configuration

Set environment variables:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

---

## 📡 API Endpoints

### Get Recommendation History
```http
GET /api/recommendations/history
  ?architecture_id=arch-123
  &limit=50
```

**Response:**
```json
{
  "source": "cache",
  "history": [
    {
      "timestamp": "2026-03-16T14:30:00",
      "status": "completed",
      "card_count": 12,
      "total_estimated_savings": 1500.50,
      "generation_time_ms": 4200
    }
  ],
  "total": 1
}
```

### Start Background Generation
```http
POST /api/recommendations/generate-bg
Content-Type: application/json

{
  "architecture_id": "arch-123",
  "use_cache": true
}
```

**Response (Cache Hit):**
```json
{
  "source": "cache",
  "recommendations": [...],
  "total_estimated_savings": 1500,
  "generation_time_ms": 45,
  "cached_at": "2026-03-16T14:30:00",
  "task_id": null
}
```

**Response (Background Task Started):**
```json
{
  "source": "background",
  "task_id": "abc123",
  "status": "queued",
  "message": "Recommendations are being generated..."
}
```

### Get Task Status
```http
GET /api/recommendations/task-status/abc123
```

**Response:**
```json
{
  "task_id": "abc123",
  "state": "PROGRESS",
  "progress": 65,
  "stage": "Generating recommendations via LLM...",
  "result": null,
  "error": null
}
```

### Get Single Result
```http
GET /api/recommendations/result/12345
```

### Clear Cache
```http
POST /api/recommendations/cache/clear
Content-Type: application/json

{
  "architecture_id": "arch-123"
}
```

### Get Summary
```http
GET /api/recommendations/summary
  ?architecture_id=arch-123
```

**Response:**
```json
{
  "total_monthly_savings": 1500.50,
  "total_annual_savings": 18006,
  "average_generation_time_ms": 4120,
  "total_recommendations": 12,
  "last_updated": "2026-03-16T14:30:00"
}
```

---

## 🎨 Frontend Integration

### Using the New Components

```jsx
import { RecommendationCard, SavingsSummary, RecommendationHistory } from './components/RecommendationCard';

function MyAnalysisPage() {
  const [recommendations, setRecommendations] = useState([]);
  const [totalSavings, setTotalSavings] = useState(0);
  const [history, setHistory] = useState([]);
  const [taskId, setTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);

  // Load recommendations
  const loadRecommendations = async () => {
    const response = await fetch('/api/recommendations/generate-bg', {
      method: 'POST',
      body: JSON.stringify({
        architecture_id: 'arch-123',
        use_cache: true,
      }),
    });
    const data = await response.json();
    
    if (data.source === 'cache') {
      setRecommendations(data.recommendations);
      setTotalSavings(data.total_estimated_savings);
    } else {
      // Start polling
      setTaskId(data.task_id);
      pollTaskStatus(data.task_id);
    }
  };

  // Poll for progress
  const pollTaskStatus = (taskId) => {
    const interval = setInterval(async () => {
      const response = await fetch(`/api/recommendations/task-status/${taskId}`);
      const status = await response.json();
      
      setTaskStatus(status);
      
      if (status.state === 'SUCCESS') {
        setRecommendations(status.result.recommendations);
        setTotalSavings(status.result.total_estimated_savings);
        clearInterval(interval);
      }
    }, 1000);
  };

  return (
    <div>
      {/* Savings at top */}
      <SavingsSummary
        totalMonthly={totalSavings}
        totalAnnual={totalSavings * 12}
        recommendationCount={recommendations.length}
        status={taskId ? 'generating' : 'completed'}
      />

      {/* Progress bar */}
      {taskStatus && (
        <div className="progress-panel">
          <p>{taskStatus.stage}</p>
          <div className="progress-bar">
            <div style={{ width: `${taskStatus.progress}%` }}></div>
          </div>
        </div>
      )}

      {/* Cards grid */}
      <div className="recommendations-grid">
        {recommendations.map(rec => (
          <RecommendationCard key={rec.id} recommendation={rec} />
        ))}
      </div>

      {/* History */}
      <RecommendationHistory 
        recommendations={history}
        onSelect={(item) => console.log(item)}
      />
    </div>
  );
}
```

---

## ⚙️ Background Tasks Configuration

### Celery Beat Schedule

Default **cron jobs** in `src/background/tasks.py`:

| Task | Schedule | Purpose |
|------|----------|---------|
| `collect_cur_data` | Every hour at :00 | Collect AWS CUR data |
| `cleanup_old_cache` | Daily at 2 AM | Clean expired cache entries |

**Modify schedule:**

```python
app.conf.beat_schedule = {
    "my-custom-task": {
        "task": "path.to.task",
        "schedule": crontab(minute=0, hour=*/3),  # Every 3 hours
    }
}
```

---

## 🐛 Troubleshooting

### Redis Not Connected
```
⚠️ Redis connection failed: ... (caching disabled)
```
- **Fix:** Start Redis service
- **Fallback:** System works without cache (but slower)

### Celery Worker Not Picking Up Tasks
```bash
# Check worker is running
celery -A src.background.tasks inspect active

# List registered tasks
celery -A src.background.tasks inspect registered

# Increase logging
celery -A src.background.tasks worker --loglevel=debug
```

### Task Status Returns PENDING
- Task not yet picked up by worker
- **Solution:** Wait a moment, or check worker logs

### CUR Collection Not Running
```bash
# Check Beat is running
celery -A src.background.tasks inspect scheduled

# Manual trigger
celery -A src.background.tasks send_task 'src.background.tasks.collect_cur_data'
```

---

## 📊 Monitoring

### Option 1: Flower (Web UI for Celery)
```bash
pip install flower
celery -A src.background.tasks flower

# Visit http://localhost:5555
```

### Option 2: Redis CLI
```bash
# Connect to Redis
redis-cli

# Monitor all keys
MONITOR

# Check cache size
INFO memory
```

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│              Frontend (React + Vite)                     │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │ Cards View │ │ History View │ │ Progress Indicator │ │
│  └──────┬─────┘ └──────┬───────┘ └─────────┬──────────┘ │
└─────────┼──────────────┼──────────────────┼─────────────┘
          │              │                  │
          │ GET /last    │ GET /history     │ POST /generate-bg
          │              │                  │ & GET /task-status
          │              │                  │
┌─────────┼──────────────┼──────────────────┼─────────────────┐
│         │              │                  │    Backend API   │
│  ┌──────▼───────────────▼──────────────────▼─────────────┐  │
│  │   Recommendation Manager                              │  │
│  │  - Deduplication & Validation                         │  │
│  │  - History Tracking                                   │  │
│  │  - Cache Management                                   │  │
│  └───────┬──────────────────────────────────┬────────────┘  │
│          │                                  │                │
│  ┌───────▼─────────────────┐    ┌──────────▼────────────┐  │
│  │  Redis Cache            │    │  PostgreSQL DB        │  │
│  │  - Current Results      │    │  - Full History       │  │
│  │  - Task Status          │    │  - Detailed Results   │  │
│  │  - History (LRU 24h)    │    │  - Metadata           │  │
│  └─────────────────────────┘    └───────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │   Celery Queue (Background Tasks)                     │  │
│  │  ┌─────────────────┐ ┌──────────────────────────────┐ │  │
│  │  │ Worker Threads  │ │ Beat Scheduler (Cron)       │ │  │
│  │  │ - Analyze       │ │ - Hourly CUR Collection     │ │  │
│  │  │ - Generate      │ │ - Daily Cache Cleanup       │ │  │
│  │  │ - Validate      │ │ - Custom Tasks              │ │  │
│  │  └─────────────────┘ └──────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 📝 File Structure

```
finops-ai-system/
├── frontend/src/
│   ├── components/
│   │   ├── RecommendationCard.jsx       ✨ New component
│   │   ├── RecommendationCard.css       ✨ New styling
│   │   └── ...
│   └── pages/
│       ├── AnalysisPageV2.jsx           ✨ New page with features
│       ├── AnalysisPageV2.css           ✨ New styling
│       └── ...
│
├── src/
│   ├── api/
│   │   ├── handlers/
│   │   │   ├── recommendations.py       ✨ New endpoints
│   │   │   └── analyze.py               (updated with caching)
│   │   └── main.py                      (updated with new routes)
│   │
│   ├── storage/
│   │   ├── recommendation_cache.py      ✨ New Redis cache
│   │   └── database.py
│   │
│   ├── background/                      ✨ New module
│   │   ├── __init__.py
│   │   └── tasks.py                     ✨ Celery tasks
│   │
│   └── ...
│
├── docker/
│   └── api/
│       └── requirements-background.txt  ✨ New dependencies
│
└── docker-compose.extended.yml          ✨ New compose with Redis/Celery
```

---

## 🎓 Example Workflows

### Workflow 1: View Cached Recommendations
```
1. User loads Analysis page
2. Frontend calls: POST /api/recommendations/generate-bg?use_cache=true
3. Backend checks Redis: Cache HIT ✓
4. Returns instantly: { source: 'cache', recommendations: [...] }
5. UI displays savings & cards immediately
6. User can expand cards or view history
```

### Workflow 2: Refresh Analysis
```
1. User clicks "Refresh Analysis" button
2. Frontend calls: POST /api/recommendations/cache/clear
3. Frontend calls: POST /api/recommendations/generate-bg?use_cache=false
4. Backend message: { source: 'background', task_id: 'xyz' }
5. Frontend starts polling: GET /api/recommendations/task-status/xyz (every 1s)
6. Shows: "10% - Loading graph..." → "30% - Analyzing..." → "70% - Generating..."
7. Completes: "100% - Saving..." 
8. Results appear in grid
9. Auto-saved to history
```

### Workflow 3: CUR Collection (Automatic)
```
Every hour at :00
  ↓
Celery Beat triggers: collect_cur_data
  ↓
Worker receives task
  ↓
Collects AWS CUR data (boto3)
  ↓
Parses cost data
  ↓
Updates PostgreSQL
  ↓
Task completed
  ↓
Next hour...
```

---

## 🎉 Summary

✅ **Stylish cards** with savings badge
✅ **Total savings** display at top  
✅ **Expandable details** on click
✅ **History view** for past runs
✅ **Background analysis** with progress
✅ **Redis caching** for instant results
✅ **Hourly CUR collection** via Celery Beat
✅ **Persistent storage** in PostgreSQL
✅ **Responsive UI** during analysis
✅ **Complete API** for all operations

All features are **production-ready** and **fully backward compatible**! 🚀
