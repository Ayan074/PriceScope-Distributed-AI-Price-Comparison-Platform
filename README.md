<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Celery-5.4+-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img src="https://img.shields.io/badge/Redis-7.0+-DC382D?style=for-the-badge&logo=redis&logoColor=white" />
  <img src="https://img.shields.io/badge/MCP-Protocol-blueviolet?style=for-the-badge" />
</p>

# 🔭 PriceScope — Distributed Price Comparison Platform

> A **distributed computing system** that searches for any product across **5 e-commerce platforms** simultaneously and returns the best deal — powered by parallel workers, task queues, circuit breakers, and fault tolerance.

Search once. Compare Amazon, eBay, Google Shopping, Walmart, and Target in parallel. Get the best price in seconds.

---

## 📐 System Architecture

```
                             USER BROWSER
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (FastAPI :8080)                         │
│                                                                         │
│   Receives search → Fan-out to workers → Collects → Normalizes → Ranks │
│   Serves frontend │ Caches results │ Health monitoring │ LLM insights   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                     Celery group() dispatch
                     (parallel fan-out via Redis)
                                 │
       ┌──────────┬──────────┬───┴───────┬──────────┬──────────┐
       ▼          ▼          ▼           ▼          ▼          │
  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐│
  │Worker 1 │ │Worker 2 │ │ Worker 3 │ │Worker 4 │ │Worker 5││
  │ Amazon  │ │  eBay   │ │  Google  │ │ Walmart │ │ Target ││
  │Selenium │ │   BS4   │ │ SerpAPI  │ │Scraping │ │SerpAPI ││
  │ :8005   │ │  :8003  │ │  :8004   │ │  :8006  │ │ :8007  ││
  └─────────┘ └─────────┘ └──────────┘ └─────────┘ └────────┘│
                                                               │
                 ┌──────────────┐              ┌───────────────┘
                 │  Redis :6379 │              │ MCP Server
                 │  • Broker    │              │   :8010
                 │  • Cache     │              │ (LLM Tools)
                 └──────────────┘              └──────────────
```

---

## ✅ Distributed Computing Features

| Feature | Implementation |
|---|---|
| **Parallel Processing** | Celery `group()` dispatches 5 tasks simultaneously across worker processes |
| **Task Queue** | Celery + Redis message broker with dedicated queues per source |
| **Multiple Workers** | 5 independent worker processes, each handling one data source |
| **Fault Tolerance** | Circuit breaker pattern (`CLOSED → OPEN → HALF_OPEN`) per source |
| **Graceful Degradation** | If 1–4 sources fail, remaining results are still returned |
| **Auto Retry** | 2 retries with exponential backoff per task |
| **Async Fallback** | If Redis is unavailable, falls back to `asyncio.gather()` parallel mode |
| **Caching** | Redis-backed cache (5-min TTL) with in-memory fallback |
| **Health Monitoring** | Real-time health checks for all microservices via `/api/health` |
| **MCP Protocol** | Model Context Protocol server exposes search/normalize/rank as LLM tools |

---

## 📦 Data Sources

| Source | Method | Prices | Port | Queue |
|--------|--------|--------|------|-------|
| **Amazon** | Selenium (headless Chrome) | INR | `8005` | `amazon` |
| **eBay** | httpx + BeautifulSoup | USD → INR | `8003` | `ebay` |
| **Google Shopping** | SerpAPI | INR | `8004` | `google` |
| **Walmart** | SerpAPI + BS4 fallback | USD → INR | `8006` | `walmart` |
| **Target** | SerpAPI (Google Shopping) | INR | `8007` | `target` |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Redis** (optional — system auto-falls back to async mode without it)
- **Chrome** (for Amazon Selenium scraper)
- **SerpAPI key** (free tier: 100 searches/month — [get one here](https://serpapi.com/))

### 1. Clone the Repository

```bash
git clone https://github.com/<your-username>/PriceScope.git
cd PriceScope
```

### 2. Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and set your API keys:

```env
# Required — powers Google Shopping, Walmart, and Target searches
SERPAPI_KEY=your_serpapi_key_here

# Optional — Redis for distributed Celery mode
REDIS_URL=redis://localhost:6379

# Optional — enables LLM-powered AI insights (OpenAI)
OPENAI_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4o-mini
```

### 5. Start Redis (Optional, for Celery Mode)

```bash
# Using Docker:
docker run -d -p 6379:6379 redis

# Or install natively (Ubuntu):
sudo apt install redis-server -y && sudo systemctl start redis

# Or on Windows (via WSL or Memurai)
```

> **💡 Without Redis:** The system automatically falls back to `asyncio.gather()` parallel mode. Everything still works — you just lose the Celery distributed task queue.

### 6. Launch All Services

```bash
python run_all.py
```

This single command starts **all 8 processes**:

| Process | Component | Port |
|---------|-----------|------|
| 1 | Amazon Service (Selenium) | `8005` |
| 2 | eBay Service (Scraping) | `8003` |
| 3 | Google Shopping Service (SerpAPI) | `8004` |
| 4 | Walmart Service (Scraping) | `8006` |
| 5 | Target Service (SerpAPI) | `8007` |
| 6 | MCP Server (LLM Tools) | `8010` |
| 7 | API Gateway + Frontend | `8080` |
| 8–9 | Celery Workers (if Redis available) | — |

### 7. Open the Frontend

Navigate to **http://localhost:8080** in your browser.

### 8. Run Tests

```bash
python test_search.py
```

### 9. Stop All Services

Press `Ctrl+C` in the terminal — all processes are gracefully terminated.

---

## 📁 Project Structure

```
PriceScope/
│
├── gateway/                         # 🌐 API Gateway (central hub)
│   ├── main.py                      # FastAPI app — serves frontend + REST API
│   ├── config.py                    # Settings: service URLs, Redis, API keys
│   ├── orchestrator.py              # Core pipeline — Celery dispatch or async fallback
│   ├── llm_engine.py                # MCP Agent + rule-based analysis engine
│   └── models.py                    # Pydantic request/response models
│
├── services/                        # 🏭 Microservices (one per data source)
│   ├── amazon/
│   │   ├── main.py                  # FastAPI :8005
│   │   └── scraper.py               # Selenium headless Chrome scraper
│   ├── ebay/
│   │   ├── main.py                  # FastAPI :8003
│   │   └── scraper.py               # httpx + BeautifulSoup scraper
│   ├── google/
│   │   ├── main.py                  # FastAPI :8004
│   │   └── scraper.py               # SerpAPI integration
│   ├── walmart/
│   │   ├── main.py                  # FastAPI :8006
│   │   └── scraper.py               # SerpAPI + BS4 hybrid scraper
│   └── target/
│       ├── main.py                  # FastAPI :8007
│       └── scraper.py               # SerpAPI (Google Shopping) scraper
│
├── celery_app/                      # ⚙️ Distributed Task Queue
│   ├── __init__.py                  # Celery config (Redis broker, queue routing)
│   ├── tasks.py                     # Worker tasks — one per source (5 total)
│   └── circuit_breaker.py           # Fault tolerance: CLOSED → OPEN → HALF_OPEN
│
├── mcp_server/                      # 🤖 Model Context Protocol Server
│   └── server.py                    # Exposes search/normalize/rank as MCP tools
│
├── shared/                          # 📚 Shared Utilities
│   ├── models.py                    # Pydantic data models (Product, SearchRequest)
│   ├── utils.py                     # Price normalization, currency conversion, scoring
│   └── cache.py                     # Redis cache + in-memory fallback
│
├── frontend/                        # 🎨 Web UI
│   ├── index.html                   # Single-page app
│   ├── styles.css                   # Premium dark theme with glassmorphism
│   └── app.js                       # Frontend logic (search, render, history)
│
├── run_all.py                       # 🚀 One-command launcher for all services
├── test_search.py                   # 🧪 End-to-end test suite
├── check_health.py                  # ❤️ Service health checker
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variable template
└── Instructions                     # Multi-machine deployment guide (3 machines)
```

---

## 🔧 How It Works (Step by Step)

```
 ① User searches "iPhone 15"
              │
              ▼
 ② Gateway receives POST /api/compare
              │
     ┌────────┴────────┐
     │   Cache check    │──── HIT → return cached result (skips workers)
     └────────┬────────┘
              │ MISS
              ▼
 ③ Orchestrator detects mode
     ┌────────┴────────┐
     │  Redis online?   │
     └──┬───────────┬──┘
      YES            NO
        │              │
        ▼              ▼
 ④a Celery group()   ④b asyncio.gather()
     dispatch          direct HTTP calls
        │              │
        ▼              ▼
 ⑤ 5 workers run IN PARALLEL
     ├── Worker 1 → Amazon (Selenium scrapes amazon.in)
     ├── Worker 2 → eBay (BS4 scrapes ebay.com)
     ├── Worker 3 → Google Shopping (SerpAPI query)
     ├── Worker 4 → Walmart (SerpAPI + scraping)
     └── Worker 5 → Target (SerpAPI query)
              │
              ▼
 ⑥ Results collected (45s timeout, fault tolerant)
     └── If any source fails → circuit breaker logs it → partial results returned
              │
              ▼
 ⑦ Normalize → Deduplicate → Rank
     ├── Convert all prices to INR
     ├── Clean product titles
     ├── Calculate value-for-money scores
     └── Filter out accessories via price clustering
              │
              ▼
 ⑧ Generate insights
     ├── Try: MCP Agent (LLM-powered analysis)
     └── Fallback: Rule-based math engine
              │
              ▼
 ⑨ Cache result (5 min TTL) → Return to frontend
```

---

## ⚡ Circuit Breaker Pattern

Each data source has an independent circuit breaker that prevents cascading failures:

```
                         ┌──────────────────────┐
                         │       CLOSED          │
                         │   (normal operation)   │
                         └──────────┬───────────┘
                                    │
                             5 consecutive
                               failures
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │        OPEN           │
                         │  (all calls blocked)  │
                         └──────────┬───────────┘
                                    │
                              60s cooldown
                                    │
                                    ▼
                         ┌──────────────────────┐
                    ┌────│     HALF_OPEN         │────┐
                    │    │  (1 test call allowed) │    │
                    │    └──────────────────────┘    │
                success                           failure
                    │                                 │
                    ▼                                 ▼
               → CLOSED                          → OPEN
              (recovered)                     (still failing)
```

**Parameters per source:**
- **Failure threshold:** 5 consecutive failures triggers OPEN state
- **Recovery timeout:** 60 seconds before allowing a test call
- **Applies to:** Amazon, eBay, Google, Walmart, Target (independently)

---

## 🌐 API Reference

### Compare Products
```http
POST /api/compare
Content-Type: application/json

{
  "query": "iPhone 15 128GB"
}
```

**Response:** Ranked products with `best_price`, `best_rating`, `best_value`, insights, and metadata.

### Health Check
```http
GET /api/health
```

Returns health status for all 5 microservices, circuit breaker states, and processing mode.

### Search History
```http
GET /api/history
```

Returns the last 20 searches with timestamps and result counts.

### Configuration Info
```http
GET /api/config
```

Returns current LLM availability, model name, and registered services.

### Individual Service Search
```http
GET http://localhost:8005/search?query=iphone    # Amazon
GET http://localhost:8003/search?query=iphone    # eBay
GET http://localhost:8004/search?query=iphone    # Google Shopping
GET http://localhost:8006/search?query=iphone    # Walmart
GET http://localhost:8007/search?query=iphone    # Target
```

---

## 🖥️ Multi-Machine Deployment (3 Nodes)

For true distributed deployment across multiple machines, see the [Instructions](./Instructions) file. Summary:

| Machine | Components | Services |
|---------|-----------|----------|
| **Machine 1** | Redis Server + Gateway | Gateway `:8080`, Redis `:6379` |
| **Machine 2** | Scraper Services | eBay `:8003`, Google `:8004` |
| **Machine 3** | Scraper Services + Workers | Amazon `:8005`, Walmart `:8006`, Target `:8007`, Celery Workers |

Update `.env` on each machine with the correct IP addresses for cross-machine communication.

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend Framework** | FastAPI | Async REST APIs for gateway + microservices |
| **Task Queue** | Celery 5.4 | Distributed task dispatch via `group()` |
| **Message Broker** | Redis 7+ | Celery broker + result backend + cache |
| **Web Scraping** | Selenium, BS4, httpx | Platform-specific scrapers |
| **Search API** | SerpAPI | Google Shopping, Walmart, Target data |
| **LLM Integration** | OpenAI + MCP | AI-powered product analysis |
| **Data Models** | Pydantic v2 | Type-safe request/response validation |
| **Frontend** | HTML + CSS + Vanilla JS | Dark-themed responsive UI |
| **Fonts** | Inter (Google Fonts) | Modern typography |

---

## 📊 Value Scoring Formula

Products are ranked using a composite value score that balances price, rating, and popularity:

```
Value Score = (Price Factor × 0.4) + (Trust Score × 0.6)

Where:
  Price Factor = 100,000 / (price_inr + 100)     ← log-scale, lower price = higher score
  Trust Score  = (rating × 20) + (log₁₀(reviews + 1) × 10)
```

The **Price Clustering** algorithm filters out accessories (cases, cables, screen protectors) by:
1. Removing products matching known accessory keywords
2. Excluding items priced below 30% of the average price

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| `Redis not available` warning | Install Redis or run `docker run -d -p 6379:6379 redis`. The system works without it using async fallback. |
| Amazon returns 0 results | Amazon actively blocks scrapers. Ensure Chrome + ChromeDriver are installed. Results may vary. |
| `SERPAPI_KEY` errors | Get a free key at [serpapi.com](https://serpapi.com/) and add it to `.env`. Google, Walmart, and Target need this. |
| Port already in use | Kill the process using the port: `netstat -ano \| findstr :8080` then `taskkill /PID <pid> /F` |
| Celery workers not starting | Check Redis is running: `redis-cli ping`. Should return `PONG`. |
| All circuit breakers OPEN | Wait 60 seconds for recovery, or restart the gateway to reset breaker states. |

---

## 📄 License

This project was built as a **Distributed Computing (GDDC)** course project. For academic use.

---

<p align="center">
  <b>Built with ❤️ using FastAPI + Celery + Redis — 5 Parallel Workers, 1 Unified Search</b>
</p>
