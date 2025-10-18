import threading
import time
import webbrowser
import os
import sys

# Add backend to import path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

try:
    from backend.server import app
    import uvicorn
    print("All imports successful")
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install fastapi uvicorn python-pptx reportlab pydub pillow aiofiles")
    input("Press Enter to exit...")
    sys.exit(1)

def run_server():
    print("Starting Music Loto Maker server...")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    except Exception as e:
        print(f"Server error: {e}")

def open_browser():
    time.sleep(3)
    try:
        webbrowser.open("http://127.0.0.1:8000")
        print("Browser opened! Open http://127.0.0.1:8000")
    except:
        print("Please open manually: http://127.0.0.1:8000")

if __name__ == "__main__":
    print("=== Music Loto Maker ===")
    
    # Create folders
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    print("Folders created")
    
    # Start server
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Server started")
    
    # Open browser
    open_browser()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Application stopped")
