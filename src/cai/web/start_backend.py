#!/usr/bin/env python3
"""
Startup script for CAI Web Backend
Sets proper environment and starts the FastAPI server
"""
import os
import sys

# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, '..', '..')
sys.path.insert(0, src_dir)

# Set default environment variables
if not os.getenv("CAI_MODEL"):
    os.environ["CAI_MODEL"] = "openrouter/z-ai/glm-4.5-air:free"

if not os.getenv("CAI_AGENT_TYPE"):
    os.environ["CAI_AGENT_TYPE"] = "one_tool_agent"

# Import and run the FastAPI app
if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting CAI Web Backend...")
    print(f"📡 Model: {os.getenv('CAI_MODEL')}")
    print(f"🤖 Default Agent: {os.getenv('CAI_AGENT_TYPE')}")
    print("🌐 Backend will be available at: http://localhost:8000")
    print("📋 API docs at: http://localhost:8000/docs")
    
    uvicorn.run(
        "cai.web.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
