#!/usr/bin/env python3
"""
CAI Web Interface Launcher
Starts both frontend and backend services for CAI web interface
"""
import os
import sys
import subprocess
import signal
import time
from pathlib import Path

def main():
    # Get the project root directory
    project_root = Path(__file__).parent
    backend_dir = project_root / "src" / "cai" / "web" / "backend"
    frontend_dir = project_root / "src" / "cai" / "web" / "frontend"
    
    # Add src to Python path
    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))
    
    # Set default environment variables
    env = os.environ.copy()
    if not env.get("CAI_MODEL"):
        env["CAI_MODEL"] = "openrouter/z-ai/glm-4.5-air:free"
    if not env.get("CAI_AGENT_TYPE"):
        env["CAI_AGENT_TYPE"] = "one_tool_agent"
    if not env.get("PYTHONPATH"):
        env["PYTHONPATH"] = str(src_dir)
    else:
        env["PYTHONPATH"] = f"{src_dir}:{env['PYTHONPATH']}"
    
    processes = []
    
    def signal_handler(signum, frame):
        print("\n🛑 Shutting down CAI Web Interface...")
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        
        # Wait a bit for graceful shutdown
        time.sleep(2)
        
        # Force kill if needed
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
        
        sys.exit(0)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("🚀 Starting CAI Web Interface...")
        print(f"📡 Model: {env.get('CAI_MODEL')}")
        print(f"🤖 Default Agent: {env.get('CAI_AGENT_TYPE')}")
        
        # Start backend
        print("🔧 Starting backend server...")
        backend_cmd = [
            sys.executable, "-m", "uvicorn", "cai.web.backend.main:app",
            "--host", "0.0.0.0", "--port", "8000", "--reload"
        ]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(project_root),
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True
        )
        processes.append(backend_proc)
        
        # Wait a moment for backend to start
        time.sleep(3)
        
        # # Start frontend  
        # print("💻 Starting frontend server...")
        # frontend_cmd = [
        #     "npm", "start"
        # ]
        # frontend_env = env.copy()
        # frontend_env.update({
        #     "PORT": "3000",
        #     "GENERATE_SOURCEMAP": "false",
        #     "REACT_APP_API_URL": "http://localhost:8000",
        #     "REACT_APP_WS_URL": "ws://localhost:8000"
        # })
        
        # frontend_proc = subprocess.Popen(
        #     frontend_cmd,
        #     cwd=str(frontend_dir),
        #     env=frontend_env,
        #     stdout=subprocess.PIPE,
        #     stderr=subprocess.STDOUT,
        #     text=True
        # )
        # processes.append(frontend_proc)
        
        print("✅ CAI Web Interface is starting...")
        print("🌐 Frontend: http://localhost:3000")
        print("🔗 Backend API: http://localhost:8000")
        print("📋 API Docs: http://localhost:8000/docs")
        print("🛑 Press Ctrl+C to stop")
        
        # Monitor processes
        while True:
            time.sleep(1)
            
            # Check if any process died
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    if i == 0:
                        print("❌ Backend process died")
                    else:
                        print("❌ Frontend process died")
                    
                    # Kill all processes and exit
                    signal_handler(signal.SIGTERM, None)
                    
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        print(f"❌ Error starting CAI Web Interface: {e}")
        signal_handler(signal.SIGTERM, None)

if __name__ == "__main__":
    main()
