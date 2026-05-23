"""
Celery Application Configuration for PriceScope.

Uses Redis as both message broker and result backend.
Each source (Amazon, eBay, Google, Walmart) gets its own dedicated queue,
and each Celery worker process handles one queue → true multi-process parallelism.

Architecture:
    Gateway → Celery group() → Redis Broker → Worker Nodes (4 processes)
                                                  ├── amazon_worker  (queue: amazon)
                                                  ├── ebay_worker    (queue: ebay)
                                                  ├── google_worker  (queue: google)
                                                  └── walmart_worker (queue: walmart)
"""

import os
from celery import Celery
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Create Celery application
app = Celery(
    'pricescope',
    broker=f'{REDIS_URL}/0',
    backend=f'{REDIS_URL}/1',
    include=['celery_app.tasks']
)

# Configuration
app.conf.update(
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # Timezone
    timezone='Asia/Kolkata',

    # Task tracking
    task_track_started=True,

    # Timeouts: hard limit 30s, soft limit 20s
    task_time_limit=30,
    task_soft_time_limit=20,

    # Do not hijack root logger
    worker_hijack_root_logger=False,

    # Route each task to its dedicated queue
    task_routes={
        'celery_app.tasks.search_amazon_task':  {'queue': 'amazon'},
        'celery_app.tasks.search_ebay_task':    {'queue': 'ebay'},
        'celery_app.tasks.search_google_task':  {'queue': 'google'},
        'celery_app.tasks.search_walmart_task': {'queue': 'walmart'},
    },

    # Default queue for any unrouted tasks
    task_default_queue='default',
)
