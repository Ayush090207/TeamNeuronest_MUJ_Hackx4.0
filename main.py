"""
Jal Drishti - Application Entry Point
=======================================
Root entry point for production and local deployment.
Imports the FastAPI app and adds static dashboard serving.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import the existing FastAPI app with all API routes
from src.api_server import app

# =============================================
# Static Dashboard Serving
# =============================================

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"

# Serve static asset directories
app.mount("/css", StaticFiles(directory=DASHBOARD_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=DASHBOARD_DIR / "js"), name="js")
app.mount("/data", StaticFiles(directory=DASHBOARD_DIR / "data"), name="data")

# Mount assets directory if it exists
assets_dir = DASHBOARD_DIR / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# =============================================
# HTML Page Routes
# =============================================

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def serve_dashboard():
    """Serve the main dashboard page."""
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/methodology", include_in_schema=False)
@app.get("/methodology.html", include_in_schema=False)
async def serve_methodology():
    """Serve the methodology page."""
    return FileResponse(DASHBOARD_DIR / "methodology.html")
