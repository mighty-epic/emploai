"""
Chat App Backend
FastAPI server with chat and agent endpoints.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Literal
import os
import sys
import json
import time
from pathlib import Path

# Add parent to path for agent imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from anthropic import Anthropic

# ============================================================
# MODELS CONFIG
# ============================================================

MODELS = {
    # OpenAI
    "gpt-5": {"provider": "openai", "id": "gpt-5"},
    "gpt-5.1": {"provider": "openai", "id": "gpt-5.1"},
    "gpt-5.2": {"provider": "openai", "id": "gpt-5.2"},
    "gpt-5.4": {"provider": "openai", "id": "gpt-5.4"},
    "gpt-5.5": {"provider": "openai", "id": "gpt-5.5"},
    "gpt-5.4-mini": {"provider": "openai", "id": "gpt-5.4-mini"},
    "gpt-4.1": {"provider": "openai", "id": "gpt-4.1"},
    "gpt-4o": {"provider": "openai", "id": "gpt-4o"},
    "gpt-4o-mini": {"provider": "openai", "id": "gpt-4o-mini"},
    
    # Anthropic
    "claude-sonnet-4.5": {"provider": "anthropic", "id": "claude-sonnet-4-5-20250929"},
    "claude-opus-4.5": {"provider": "anthropic", "id": "claude-opus-4-5-20250929"},
    "claude-sonnet-4.6": {"provider": "anthropic", "id": "claude-sonnet-4-6"},
    "claude-opus-4.6": {"provider": "anthropic", "id": "claude-opus-4-6"},
    "claude-opus-4.7": {"provider": "anthropic", "id": "claude-opus-4-7"},
    "claude-opus": {"provider": "anthropic", "id": "claude-opus-4-20250514"},
    "claude-haiku": {"provider": "anthropic", "id": "claude-haiku-4-20250514"},
    "claude-sonnet-3.5": {"provider": "anthropic", "id": "claude-3-5-sonnet-20241022"},
}

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(title="AI Chat with Agent")

# Clients
openai_client = OpenAI()
anthropic_client = Anthropic()

# Chat memory (persists across model switches)
chat_memory: List[Dict] = []

# ============================================================
# MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str
    model: str = "claude-sonnet-3.5"

class AgentRequest(BaseModel):
    task: str
    model: str = "claude-sonnet-3.5"

class ChatResponse(BaseModel):
    response: str
    model: str

class AgentResponse(BaseModel):
    success: bool
    summary: str
    actions: List[Dict]
    screenshots: List[str]
    model: str

# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global chat_memory
    
    model_config = MODELS.get(request.model)
    if not model_config:
        raise HTTPException(status_code=400, detail=f"Unknown model: {request.model}")
    
    # Add user message to memory
    chat_memory.append({"role": "user", "content": request.message})
    
    try:
        if model_config["provider"] == "openai":
            response = openai_client.chat.completions.create(
                model=model_config["id"],
                messages=chat_memory
            )
            assistant_message = response.choices[0].message.content
        
        elif model_config["provider"] == "anthropic":
            # Anthropic format
            response = anthropic_client.messages.create(
                model=model_config["id"],
                max_tokens=4096,
                messages=chat_memory
            )
            assistant_message = response.content[0].text
        
        else:
            raise HTTPException(status_code=500, detail="Unknown provider")
        
        # Add assistant response to memory
        chat_memory.append({"role": "assistant", "content": assistant_message})
        
        return ChatResponse(response=assistant_message, model=request.model)
    
    except Exception as e:
        # Remove failed user message
        chat_memory.pop()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# AGENT ENDPOINT
# ============================================================

from fastapi.responses import StreamingResponse
import queue
import threading

# Global event queue for streaming
agent_events = queue.Queue()

def event_callback(event_type: str, data: dict):
    """Callback for agent events."""
    agent_events.put({"type": event_type, "data": data})

@app.post("/api/agent", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    """Execute task with agent orchestrator."""
    try:
        # Import agent
        from agent.orchestrator import AgentOrchestrator
        
        agent = AgentOrchestrator(model=request.model)
        result = agent.execute_task(request.task)
        
        return AgentResponse(
            success=result["success"],
            summary=result["summary"],
            actions=result.get("actions", []),
            screenshots=result.get("screenshots", []),
            model=request.model
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return AgentResponse(
            success=False,
            summary=f"Error: {str(e)}",
            actions=[],
            screenshots=[],
            model=request.model
        )

@app.get("/api/agent/stream")
async def stream_agent(task: str, model: str = "claude-sonnet-3.5"):
    """Stream agent updates with thinking and actions via SSE."""
    
    def generate():
        try:
            from agent.orchestrator import AgentOrchestrator
            
            agent = AgentOrchestrator(model=model)
            
            # Use streaming generator
            for event in agent.execute_task_streaming(task):
                yield f"data: {json.dumps(event, default=str)}\n\n"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

# ============================================================
# UTILITY ENDPOINTS
# ============================================================

@app.post("/api/reset")
async def reset_chat():
    """Clear chat memory."""
    global chat_memory
    chat_memory = []
    return {"status": "ok", "message": "Chat memory cleared"}

@app.get("/api/models")
async def get_models():
    """Get available models."""
    return {"models": list(MODELS.keys())}

@app.get("/api/memory")
async def get_memory():
    """Get current chat memory."""
    return {"messages": chat_memory}

# ============================================================
# STATIC FILES
# ============================================================

# Serve frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Serve screenshots
screenshots_path = Path(__file__).parent.parent / "static" / "screenshots"
screenshots_path.mkdir(parents=True, exist_ok=True)
app.mount("/static/screenshots", StaticFiles(directory=str(screenshots_path)), name="screenshots")

@app.get("/")
async def root():
    """Serve main page."""
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Frontend not found. API is running."}

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
