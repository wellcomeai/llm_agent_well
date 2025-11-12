"""
FastAPI server with SSE streaming for Travel Agent V2 (Plan-and-Execute).

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
from fastapi.responses import HTMLResponse, JSONResponse
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
    title="Travel Agent Multi-Strategy API",
    description="Travel planning agent with Multi-Strategy Router (Simple/ReAct/Plan-Execute)",
    version="3.0.0"
)

# CORS middleware
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

# Initialize agent (singleton)
agent = None


def get_agent() -> TravelAgent:
    """Get or create agent instance"""
    global agent
    if agent is None:
        try:
            agent = TravelAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"),
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
    events: list
    total_events: int
    timestamp: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend HTML page."""
    html_path = Path(__file__).parent.parent / "frontend" / "index.html"

    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        get_agent()
        agent_status = "healthy"
    except Exception as e:
        agent_status = f"error: {str(e)}"

    return JSONResponse({
        "status": "healthy",
        "version": "2.0.0",
        "architecture": "plan-and-execute",
        "timestamp": datetime.now().isoformat(),
        "agent_status": agent_status,
        "environment": {
            "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "model_name": os.getenv("MODEL_NAME", "gpt-4o-mini")
        }
    })


@app.get("/api/stream")
async def stream_agent_response(
    request: Request,
    q: str,
    session_id: Optional[str] = None
):
    """
    SSE streaming endpoint for agent responses with Multi-Strategy Router.

    Query params:
        q: User query
        session_id: Optional session ID for conversation memory

    SSE Events:
        Common:
        - start: Agent started
        - routing_start/routing_complete: Query routing (includes strategy)
        - done: Processing complete (includes strategy type)
        - error: Error occurred

        SIMPLE Strategy:
        - simple_answer: Direct answer for simple queries

        REACT Strategy:
        - strategy: Strategy info (name="ReAct")
        - react_start: ReAct agent started
        - react_thought: Reasoning step
        - react_action: Tool action
        - react_observation: Tool result
        - react_complete: ReAct finished

        PLAN_EXECUTE Strategy:
        - strategy: Strategy info (name="Plan-and-Execute")
        - planning_start/plan_created: Plan creation
        - execution_start/execution_complete: Plan execution
        - step_started/step_completed/step_failed: Individual step events
        - reflection_start/reflection_complete: Result reflection
        - final_answer: Final answer
        - needs_user_input: Needs user information
        - replan: Creating new plan
    """
    if not q or q.strip() == "":
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    async def event_generator():
        """Generate SSE events from agent stream"""
        try:
            agent_instance = get_agent()

            # Stream agent events (using process_query method for V2)
            async for event in agent_instance.process_query(q, session_id):
                # Check if client disconnected
                if await request.is_disconnected():
                    print(f"Client disconnected for session {session_id}")
                    break

                # Get event type and data
                event_type = event.get("event", "unknown")
                event_data = event.get("data", {})

                # Send SSE event
                yield {
                    "event": event_type,
                    "data": json.dumps(event_data, ensure_ascii=False)
                }

                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.05)

        except Exception as e:
            # Send error event
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(e),
                    "type": type(e).__name__,
                    "timestamp": datetime.now().isoformat()
                }, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())


@app.post("/api/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Non-streaming endpoint for testing purposes.
    Returns all events at once after completion.

    Request body:
        {
            "query": "user query",
            "session_id": "optional-session-id"
        }

    Response:
        {
            "session_id": "session-id",
            "events": [...],
            "total_events": 10,
            "timestamp": "2025-01-15T10:30:00Z"
        }
    """
    try:
        agent_instance = get_agent()

        # Collect all events
        events = []
        session_id = request.session_id or f"session_{datetime.now().timestamp()}"

        async for event in agent_instance.process_query(request.query, session_id):
            events.append(event)

        return QueryResponse(
            session_id=session_id,
            events=events,
            total_events=len(events),
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
    print("🧳 Travel Agent V2 API Starting (Plan-and-Execute)...")
    print("=" * 60)
    print(f"Environment:")
    print(f"  - OpenAI API Key: {'✓ Set' if os.getenv('OPENAI_API_KEY') else '✗ Not set'}")
    print(f"  - Model: {os.getenv('MODEL_NAME', 'gpt-4o-mini')}")
    print(f"  - Temperature: {os.getenv('TEMPERATURE', '0.7')}")
    print(f"  - Architecture: Plan-and-Execute")
    print(f"  - Debug: {os.getenv('DEBUG', 'false')}")
    print("=" * 60)

    # Pre-initialize agent to catch errors early
    try:
        get_agent()
        print("✓ Agent initialized successfully (Plan-and-Execute)")
    except Exception as e:
        print(f"✗ Agent initialization failed: {e}")
        print("  Make sure OPENAI_API_KEY is set in .env file")

    print("=" * 60)
    print("Server is ready!")
    print("Open http://localhost:8000 in your browser")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global agent
    print("\nShutting down Travel Agent API...")
    if agent:
        agent.shutdown()


# ============================================================================
# MAIN
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
