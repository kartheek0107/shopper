"""
Gunicorn Configuration for Production Deployment
=================================================

Usage:
    gunicorn -c gunicorn_config.py main:app

This replaces `python main.py` (single Uvicorn process) with a
multi-worker setup that can handle 1,000+ concurrent users.
"""

import multiprocessing
import os

# ──────────────────────────────────────────────
# Server socket
# ──────────────────────────────────────────────
bind = os.getenv("BIND", "0.0.0.0:8000")

# ──────────────────────────────────────────────
# Worker configuration
# ──────────────────────────────────────────────
# Use Uvicorn's async worker class so FastAPI's async endpoints
# run on a proper asyncio event loop inside each worker.
worker_class = "uvicorn.workers.UvicornWorker"

# (2 × CPU cores) + 1 — standard Gunicorn recommendation.
# Override with WEB_CONCURRENCY env var if needed.
workers = int(os.getenv("WEB_CONCURRENCY", (2 * multiprocessing.cpu_count()) + 1))

# ──────────────────────────────────────────────
# Timeouts
# ──────────────────────────────────────────────
# Max seconds a worker can be silent before being killed and restarted.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

# Seconds to wait for workers to finish serving requests during reload.
graceful_timeout = 30

# Keep-alive connections (seconds).  Matches typical load-balancer defaults.
keepalive = 5

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
accesslog = "-"           # stdout
errorlog = "-"            # stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# ──────────────────────────────────────────────
# Process naming
# ──────────────────────────────────────────────
proc_name = "shopper-api"

# ──────────────────────────────────────────────
# Restart on high memory (safety net)
# ──────────────────────────────────────────────
max_requests = int(os.getenv("MAX_REQUESTS", "1000"))
max_requests_jitter = 50
