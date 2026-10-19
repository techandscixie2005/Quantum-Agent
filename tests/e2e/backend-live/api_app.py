"""Test-only Uvicorn entrypoint; no route or production failpoint is added.

PostgreSQL uses the production lifespan/checkpointer unchanged. SQLite is an
explicit baseline with process-local checkpoints; restart durability tests skip it.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from quantum_agent.config import Settings
from quantum_agent.knowledge.barrier_scope import load_reviews
from quantum_agent.knowledge.retrieval import HybridRetrievalConfig
from quantum_agent.main import create_app

settings = Settings(_env_file=None)
if settings.environment != "test" or urlsplit(settings.ustc_base_url).hostname != "127.0.0.1":
    raise RuntimeError("Synthetic harness requires ENVIRONMENT=test and a local provider stub")
app = create_app(settings)
fixture_reviews = load_reviews(
    Path(os.environ["BACKEND_LIVE_SOURCE_REVIEWS"]),
    os.environ["BACKEND_LIVE_SOURCE_REVIEWS_SHA256"],
    allow_test_double=True,
)
# Supply explicit synthetic fixture status to the real retriever; all SQL,
# hash/scope/applicability checks and production retrieval logic still run.
app.state.hybrid_retriever._config = HybridRetrievalConfig(barrier_source_reviews=fixture_reviews)
if settings.is_sqlite:
    app.state.teaching_workflow._enable_hitl = True
