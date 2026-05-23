# PriceScope — Distributed Price Comparison Platform

A **distributed computing project** that searches for any product across **4 e-commerce platforms** simultaneously and returns the best deal — powered by parallel workers, task queues, and fault tolerance.

## 🏗️ Architecture

```
                         USER BROWSER
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI :8000)                       │
│                                                                      │
│   Receives search → Dispatches to workers → Collects → Ranks       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                    Celery group() dispatch
                    (parallel fan-out via Redis)
                                │
         ┌──────────┬───────────┼────────────┬──────────┐
         ▼          ▼           ▼            ▼          ▼
    ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐   │
    │Worker 1 │ │Worker 2 │ │ Worker 3 │ │Worker 4 │   │
    │ Amazon  │ │  eBay   │ │  Google  │ │ Walmart │   │
    │Selenium │ │   BS4   │ │ SerpAPI  │ │Scraping │   │
    │ :8005   │ │  :8003  │ │  :8004   │ │  :8006  │   │
    └─────────┘ └─────────┘ └──────────┘ └─────────┘   │
                                                         │
                   ┌──────────────┐           ┌──────────┴──┐
                   │  Redis :6379 │           │ MCP Server  │
                   │  • Broker    │           │   :8010     │
                   │  • Cache     │           └─────────────┘
                   └──────────────┘
```

## ✅ Distributed Computing Features

| Feature | Implementation |
|---------|---------------|
| **Parallel Processing** | Celery `group()` dispatches 4 tasks simultaneously |
| **Task Queue** | Celery + Redis broker with dedicated queues per source |
| **Multiple Workers** | 4 worker processes, each handling a data source |
| **Fault Tolerance** | Circuit breaker pattern (CLOSED→OPEN→HALF_OPEN) |
| **Graceful Degradation** | If 1-3 sources fail, remaining results still returned |
| **Auto Retry** | 2 retries with exponential backoff per task |
| **Fallback Mode** | If Redis unavailable, uses `asyncio.gather()` |

## 📦 Data Sources

| Source | Method | Prices | Port |
|--------|--------|--------|------|
| Amazon | Selenium (headless Chrome) | INR | 8005 |
| eBay | httpx + BeautifulSoup | USD → INR | 8003 |
| Google Shopping | SerpAPI | INR | 8004 |
| Walmart | SerpAPI + BS4 fallback | USD → INR | 8006 |

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your SERPAPI_KEY
```

### 3. Start Redis (optional, for Celery mode)

```bash
# Using Docker:
docker run -d -p 6379:6379 redis

# Or install Redis natively
```

### 4. Start All Services

```bash
python run_all.py
```

This starts:
- 4 microservices (Amazon, eBay, Google, Walmart)
- 2 Celery workers (if Redis available)
- MCP Server
- API Gateway

### 5. Open the Frontend

Navigate to **http://localhost:8000**

### 6. Test

```bash
python test_search.py
```

## 📁 Project Structure

```
GDDc_project1/
├── celery_app/              # Distributed task queue
│   ├── __init__.py          # Celery config (Redis broker)
│   ├── tasks.py             # Worker tasks (4 sources)
│   └── circuit_breaker.py   # Fault tolerance pattern
├── services/                # Microservices (one per source)
│   ├── amazon/
│   │   ├── main.py          # FastAPI :8005
│   │   └── scraper.py       # Selenium scraper
│   ├── ebay/
│   │   ├── main.py          # FastAPI :8003
│   │   └── scraper.py       # BS4 lightweight scraper
│   ├── google/
│   │   ├── main.py          # FastAPI :8004
│   │   └── scraper.py       # SerpAPI integration
│   └── walmart/
│       ├── main.py          # FastAPI :8006
│       └── scraper.py       # SerpAPI + BS4 fallback
├── gateway/                 # API Gateway
│   ├── main.py              # FastAPI :8000
│   ├── config.py            # Service URLs + settings
│   ├── orchestrator.py      # Celery dispatch + async fallback
│   └── llm_engine.py        # Rule-based analysis
├── mcp_server/
│   └── server.py            # MCP tools for LLM integration
├── shared/
│   ├── models.py            # Pydantic models
│   ├── utils.py             # Normalization, currency conversion
│   └── cache.py             # Redis + in-memory caching
├── frontend/
│   ├── index.html           # UI
│   ├── styles.css           # Premium dark theme
│   └── app.js               # Frontend logic
├── run_all.py               # Launch all services + workers
├── test_search.py           # Test suite
├── requirements.txt         # Python dependencies
└── .env                     # Configuration
```

## 🔧 How It Works (Step by Step)

1. **User searches** "iPhone 15" on the frontend
2. **Gateway** receives `POST /api/compare` → checks cache
3. **Orchestrator** detects processing mode (Celery or Async)
4. **Celery `group()`** dispatches 4 tasks to Redis queues
5. **Worker 1** (Amazon queue) → calls Amazon microservice → Selenium scrapes amazon.in
6. **Worker 2** (eBay queue) → calls eBay microservice → BS4 scrapes ebay.com
7. **Worker 3** (Google queue) → calls Google microservice → SerpAPI query
8. **Worker 4** (Walmart queue) → calls Walmart microservice → SerpAPI/scraping
9. **All run in parallel** — 4 separate OS processes (true multiprocessing)
10. **Gateway collects** results with 20-second timeout
11. **If any source fails** → circuit breaker records failure → remaining results returned
12. **Normalize** prices to INR → **Deduplicate** → **Rank** (best price, rating, value)
13. **Cache** result for 5 minutes → **Return** to frontend

## ⚡ Circuit Breaker States

```
CLOSED (healthy) ──[5 failures]──→ OPEN (blocked)
     ↑                                    │
     │                              [60s cooldown]
     │                                    │
     └───────[success]──── HALF_OPEN ←────┘
                          (1 test request)
```
