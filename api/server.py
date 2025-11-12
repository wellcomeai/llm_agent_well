"""
FastAPI server with SSE streaming for Travel Agent.

Endpoints:
- GET /               - Serve frontend HTML
- GET /health         - Health check
- GET /api/stream     - SSE streaming endpoint
- POST /api/query     - Non-streaming endpoint (for testing)
"""

import os
import json
import asyncio
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv

# Import our agent
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.travel_agent import TravelAgent

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Travel Agent MVP API",
    description="Travel planning agent with ReAct pattern and Google ADK",
    version="1.0.0"
)

# CORS middleware (если нужно для кросс-доменных запросов)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production ограничить конкретными доменами
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize agent (singleton для MVP)
agent = None


def get_agent() -> TravelAgent:
    """Get or create agent instance"""
    global agent
    if agent is None:
        try:
            agent = TravelAgent(
                api_key=os.getenv("GOOGLE_API_KEY"),
                model_name=os.getenv("MODEL_NAME", "gemini-2.0-flash-exp"),
                temperature=float(os.getenv("TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("MAX_TOKENS", "2000"))
            )
        except Exception as e:
            print(f"Error initializing agent: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize agent: {str(e)}"
            )
    return agent


# Request/Response models
class QueryRequest(BaseModel):
    """Request model for /api/query endpoint"""
    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for /api/query endpoint"""
    session_id: str
    steps: list
    total_steps: int
    timestamp: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """
    Serve the frontend HTML page.
    """
    html_path = Path(__file__).parent.parent / "frontend" / "index.html"

    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)


@app.get("/health")
async def health_check():
    """
    Health check endpoint (для мониторинга, Render, etc.)
    """
    try:
        # Проверяем, что агент может быть инициализирован
        get_agent()
        agent_status = "healthy"
    except Exception as e:
        agent_status = f"error: {str(e)}"

    return JSONResponse({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "agent_status": agent_status,
        "environment": {
            "google_api_key_set": bool(os.getenv("GOOGLE_API_KEY")),
            "model_name": os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")
        }
    })


@app.get("/api/stream")
async def stream_agent_response(
    request: Request,
    q: str,
    session_id: Optional[str] = None
):
    """
    SSE streaming endpoint for agent responses.

    Query params:
        q: User query
        session_id: Optional session ID for conversation memory

    SSE Events:
        - start: Agent started processing
        - step: Each ReAct step (think/act/observe)
        - done: Final answer
        - error: Error occurred
    """
    if not q or q.strip() == "":
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    async def event_generator():
        """Generate SSE events from agent stream"""
        try:
            agent_instance = get_agent()

            # Send initial event
            yield {
                "event": "start",
                "data": json.dumps({
                    "message": "Agent started processing",
                    "query": q,
                    "timestamp": datetime.now().isoformat()
                }, ensure_ascii=False)
            }

            # Stream agent steps
            async for step in agent_instance.run(q, session_id):
                # Check if client disconnected
                if await request.is_disconnected():
                    print(f"Client disconnected for session {session_id}")
                    break

                # Send step event
                event_type = step["step_type"]

                yield {
                    "event": event_type,
                    "data": json.dumps(step, ensure_ascii=False)
                }

                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.1)

        except Exception as e:
            # Send error event
            yield {
                "event": "error",
                "data": json.dumps({
                    "step_type": "error",
                    "content": f"Server error: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"error_type": type(e).__name__}
                }, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())


@app.post("/api/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Non-streaming endpoint for testing purposes.
    Returns all steps at once after completion.

    Request body:
        {
            "query": "user query",
            "session_id": "optional-session-id"
        }

    Response:
        {
            "session_id": "session-id",
            "steps": [...],
            "total_steps": 5,
            "timestamp": "2025-01-15T10:30:00Z"
        }
    """
    try:
        agent_instance = get_agent()

        # Collect all steps
        steps = []
        session_id = request.session_id or f"session_{datetime.now().timestamp()}"

        async for step in agent_instance.run(request.query, session_id):
            steps.append(step)

        return QueryResponse(
            session_id=session_id,
            steps=steps,
            total_steps=len(steps),
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    print("=" * 60)
    print("🧳 Travel Agent MVP API Starting...")
    print("=" * 60)
    print(f"Environment:")
    print(f"  - Google API Key: {'✓ Set' if os.getenv('GOOGLE_API_KEY') else '✗ Not set'}")
    print(f"  - Model: {os.getenv('MODEL_NAME', 'gemini-2.0-flash-exp')}")
    print(f"  - Temperature: {os.getenv('TEMPERATURE', '0.7')}")
    print(f"  - Debug: {os.getenv('DEBUG', 'false')}")
    print("=" * 60)

    # Pre-initialize agent to catch errors early
    try:
        get_agent()
        print("✓ Agent initialized successfully")
    except Exception as e:
        print(f"✗ Agent initialization failed: {e}")
        print("  Make sure GOOGLE_API_KEY is set in .env file")

    print("=" * 60)
    print("Server is ready!")
    print("Open http://localhost:8000 in your browser")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("\nShutting down Travel Agent API...")


# ============================================================================
# MAIN (для локального запуска через python api/server.py)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )
