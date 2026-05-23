"""
run_all.py — Launches all microservices, Celery workers, and the gateway.

Distributed Architecture:
    ┌───────────────────────────────────────────────────────────┐
    │  Process 1:  Amazon Service      (port 8005) — Selenium  │
    │  Process 2:  eBay Service        (port 8003) — BS4       │
    │  Process 3:  Google Service      (port 8004) — SerpAPI   │
    │  Process 4:  Walmart Service     (port 8006) — Scraping  │
    │  Process 5:  MCP Server          (port 8010) — LLM Tools │
    │  Process 6:  API Gateway         (port 8000) — FastAPI   │
    │  Process 7:  Celery Worker 1     (queues: amazon, ebay)  │
    │  Process 8:  Celery Worker 2     (queues: google,walmart)│
    └───────────────────────────────────────────────────────────┘

Usage:
    python run_all.py

Press Ctrl+C to stop all services.
"""

import subprocess
import sys
import time
import signal
import os

import httpx

# Project root
ROOT = os.path.dirname(os.path.abspath(__file__))

# ─── Microservices ───────────────────────────────────────────────────────────

SERVICES = [
    {
        "name": "Amazon Service (Selenium)",
        "module": "services.amazon.main:app",
        "port": 8005,
    },
    {
        "name": "eBay Service (Scraping)",
        "module": "services.ebay.main:app",
        "port": 8003,
    },
    {
        "name": "Google Shopping Service (SerpAPI)",
        "module": "services.google.main:app",
        "port": 8004,
    },
    {
        "name": "Walmart Service (Scraping)",
        "module": "services.walmart.main:app",
        "port": 8006,
    },
    {
        "name": "Target Service (SerpAPI)",
        "module": "services.target.main:app",
        "port": 8007,
    },
    {
    "name": "MCP Server (LLM Tools)",
    "script": "mcp_server/server.py",
    "port": 8010,
    "env": {"PORT": "8010",}
    },
    {
        "name": "API Gateway",
        "script": "gateway/main.py",
        "port": 8080,
    },
]

# ─── Celery Workers ──────────────────────────────────────────────────────────

CELERY_WORKERS = [
    {
        "name": "Celery Worker 1 (Amazon + eBay)",
        "queues": "amazon,ebay",
        "hostname": "worker1@pricescope",
    },
    {
        "name": "Celery Worker 2 (Google + Walmart+ Target)",
        "queues": "google,walmart,Target",
        "hostname": "worker2@pricescope",
    },
]

processes: list[subprocess.Popen] = []


def start_services():
    """Start all microservices as background processes."""
    print("\n" + "=" * 65)
    print("  🚀  PriceScope — Distributed Price Comparison Platform")
    print("=" * 65 + "\n")
    print("  Starting microservices...\n")

    for service in SERVICES:
        print(f"  ▸ {service['name']} (port {service['port']})...", end=" ")

        if "script" in service:
            cmd = [sys.executable, service["script"]]
        else:
            cmd = [
                sys.executable, "-m", "uvicorn",
                service["module"],
                "--host", "0.0.0.0",
                "--port", str(service["port"]),
                "--log-level", "warning",
            ]

        env = os.environ.copy()
        if "env" in service:
            env.update(service["env"])

        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=None,
            stderr=None,
            env=env,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        processes.append(proc)
        print(f"PID {proc.pid} ✓")


def start_celery_workers():
    """Start Celery workers for distributed task processing."""
    print("\n  Starting Celery workers...\n")

    # Check if Redis is available
    try:
        import redis
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(redis_url, socket_timeout=2)
        r.ping()
        print("  ✅ Redis is running — starting Celery workers\n")
    except Exception as e:
        print(f"  ⚠️  Redis not available ({e})")
        print("  ⚠️  Celery workers SKIPPED — using async parallel mode instead")
        print("  💡 To enable distributed task queue: install and start Redis\n")
        return

    for worker in CELERY_WORKERS:
        print(f"  ▸ {worker['name']}...", end=" ")

        cmd = [
            sys.executable, "-m", "celery",
            "-A", "celery_app",
            "worker",
            "--pool=solo",
            f"--queues={worker['queues']}",
            f"--hostname={worker['hostname']}",
            "--loglevel=info",
            "--without-heartbeat",
            "--without-mingle",
            "--without-gossip",
        ]

        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=None,
            stderr=None,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        processes.append(proc)
        print(f"PID {proc.pid} ✓")


def wait_for_services(timeout: int = 90):
    """Wait until all microservices respond to health checks."""
    print("\n  ⏳ Waiting for services to become healthy...\n")

    start = time.time()
    healthy = set()

    # Only check HTTP services (not Celery workers)
    http_services = [s for s in SERVICES if "port" in s]

    while time.time() - start < timeout:
        for service in http_services:
            if service["port"] in healthy:
                continue
            
            # Determine correct health URL based on the service port
            if service["port"] == 8000:
                # Gateway specific health route
                check_url = f"http://localhost:{service['port']}/api/health"
            elif service["port"] == 8010:
                # MCP Server (SSE) might not have standard REST routes, checking root
                check_url = f"http://localhost:{service['port']}/"
            else:
                # Standard microservices
                check_url = f"http://localhost:{service['port']}/health"

            try:
                resp = httpx.get(check_url, timeout=2.0)
                # Accept 200, or 404/405 if the route isn't perfectly mapped but the server is alive
                if resp.status_code in [200, 404, 405]:
                    healthy.add(service["port"])
                    print(f"  ✅ {service['name']} — ready")
            except Exception:
                pass            
                    
        if len(healthy) >= len(http_services):
            break

        time.sleep(1.5)

    if len(healthy) < len(http_services):
        unhealthy = [s["name"] for s in http_services if s["port"] not in healthy]
        print(f"\n  ⚠️  Some services slow to start: {', '.join(unhealthy)}")
        print("  💡 They may still become available — continuing anyway")
    else:
        print(f"\n  ✅ All {len(http_services)} services are ready!\n")


def print_urls():
    """Print access URLs."""
    print("=" * 65)
    print("  📍 Access Points:")
    print("=" * 65)
    print()
    print("  🌐 Frontend:       http://localhost:8080")
    print("  📖 API Docs:       http://localhost:8080/docs")
    print("  🔍 Compare API:    POST http://localhost:8080/api/compare")
    print("  ❤️  Health Check:   http://localhost:8080/api/health")
    print()
    print("  Microservices:")
    print("    Amazon:          http://localhost:8005/search?query=iphone")
    print("    eBay:            http://localhost:8003/search?query=iphone")
    print("    Google:          http://localhost:8004/search?query=iphone")
    print("    Walmart:         http://localhost:8006/search?query=iphone")
    print("    Target:          http://localhost:8007/search?query=iphone")
    print()
    print("=" * 65)
    print("  Press Ctrl+C to stop all services")
    print("=" * 65 + "\n")


def stop_all():
    """Gracefully stop all services."""
    print("\n\n  🛑 Stopping all services...\n")

    for proc in processes:
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("  ✅ All services stopped.\n")


def main():
    def signal_handler(sig, frame):
        stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        start_services()
        start_celery_workers()
        wait_for_services()
        print_urls()

        # Keep running, monitor process health
        while True:
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    if i < len(SERVICES):
                        name = SERVICES[i]["name"]
                    else:
                        idx = i - len(SERVICES)
                        name = CELERY_WORKERS[idx]["name"] if idx < len(CELERY_WORKERS) else "Unknown"
                    print(f"  ⚠️  {name} exited with code {proc.returncode}")
            time.sleep(5)

    except KeyboardInterrupt:
        stop_all()


if __name__ == "__main__":
    main()