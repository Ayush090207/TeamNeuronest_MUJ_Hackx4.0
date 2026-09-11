"""
Jal Drishti - FastAPI Backend Server
=============================================
REST API for serving flood simulation data, risk assessments,
and resource allocation plans to the Mission Control dashboard.

Usage:
    uvicorn src.api_server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import logging

from .config import API_CONFIG, VILLAGES, SIMULATION
from .data_ingestion import DataIngestionPipeline
from .flood_model import FloodSimulationModel
from .resource_allocator import ResourceAllocator
from .rescue_path import RescuePathFinder

# =============================================
# App Initialization
# =============================================

app = FastAPI(
    title="Jal Drishti API",
    description="AI-Driven Flood Intelligence & Mission Control Backend",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CONFIG["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# Initialize services
data_pipeline = DataIngestionPipeline("dashboard/data")
flood_model = FloodSimulationModel()

# =============================================
# Request/Response Models
# =============================================

class SimulationRequest(BaseModel):
    village_id: str = Field(..., description="Village identifier")
    rainfall_mm: float = Field(50.0, ge=0, le=500, description="Rainfall in mm")


class SimulationResponse(BaseModel):
    village_id: str
    rainfall_mm: float
    time_steps: Dict
    metadata: Dict


class ResourceRequest(BaseModel):
    village_id: str
    resources: Dict[str, int] = Field(
        default={"boats": 10, "ambulances": 5, "personnel": 50},
        description="Available resource counts"
    )


class VillageInfo(BaseModel):
    id: str
    name: str
    state: str
    district: str
    terrain_type: str
    population: int
    coordinates: Dict[str, float]


class HealthResponse(BaseModel):
    status: str
    version: str
    villages_loaded: int
    data_complete: bool


# =============================================
# API Endpoints
# =============================================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health and readiness check."""
    return HealthResponse(
        status="operational",
        version="1.0.0",
        villages_loaded=len(VILLAGES),
        data_complete=all(
            data_pipeline.validate_dataset(vid)["complete"]
            for vid in VILLAGES
        ),
    )


@app.get("/api/villages", response_model=List[VillageInfo])
async def list_villages():
    """List all supported villages with metadata."""
    return [
        VillageInfo(
            id=vid,
            name=v["name"],
            state=v["state"],
            district=v["district"],
            terrain_type=v["terrain_type"],
            population=v["population"],
            coordinates=v["coordinates"],
        )
        for vid, v in VILLAGES.items()
    ]


@app.get("/api/villages/{village_id}")
async def get_village(village_id: str):
    """Get detailed information for a specific village."""
    if village_id not in VILLAGES:
        raise HTTPException(status_code=404, detail=f"Village '{village_id}' not found")

    village = VILLAGES[village_id]
    boundary = data_pipeline.load_boundary(village_id)
    buildings = data_pipeline.load_buildings(village_id)
    safe_havens = data_pipeline.load_safe_havens(village_id)
    rescue_centers = data_pipeline.load_rescue_centers(village_id)
    elevation = data_pipeline.load_elevation_profile(village_id)
    clusters = data_pipeline.load_population_clusters(village_id)

    return {
        "village": village,
        "boundary": boundary,
        "buildings_count": len(buildings.get("features", [])) if buildings else 0,
        "safe_havens": len(safe_havens),
        "rescue_centers": len(rescue_centers),
        "elevation_profile": elevation,
        "population_clusters": len(clusters),
    }


@app.post("/api/simulate", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    """
    Run flood simulation for a village with given rainfall.
    """
    if request.village_id not in VILLAGES:
        raise HTTPException(status_code=404, detail="Village not found")

    village = VILLAGES[request.village_id]
    results = flood_model.simulate(
        terrain_type=village["terrain_type"],
        bbox=tuple(village["bbox"]),
        rainfall_mm=request.rainfall_mm,
    )

    return SimulationResponse(
        village_id=request.village_id,
        rainfall_mm=request.rainfall_mm,
        time_steps=results["time_steps"],
        metadata=results["metadata"],
    )


@app.get("/api/boundary/{village_id}")
async def get_boundary(village_id: str):
    """Get village boundary GeoJSON."""
    boundary = data_pipeline.load_boundary(village_id)
    if boundary is None:
        raise HTTPException(status_code=404, detail="Boundary data not found")
    return boundary


@app.get("/api/safe-havens/{village_id}")
async def get_safe_havens(village_id: str):
    """Get safe haven locations for a village."""
    havens = data_pipeline.load_safe_havens(village_id)
    return {"type": "FeatureCollection", "features": havens}


@app.get("/api/risk-zones/{village_id}")
async def get_risk_zones(village_id: str):
    """Get pre-computed risk zones for a village."""
    zones = data_pipeline.load_risk_zones(village_id)
    return {"type": "FeatureCollection", "features": zones}


@app.post("/api/optimize-resources")
async def optimize_resources(request: ResourceRequest):
    """
    Run resource allocation optimization for a village.
    """
    if request.village_id not in VILLAGES:
        raise HTTPException(status_code=404, detail="Village not found")

    clusters = data_pipeline.load_population_clusters(request.village_id)
    rescue_centers = data_pipeline.load_rescue_centers(request.village_id)

    if not clusters or not rescue_centers:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for optimization"
        )

    # Extract center coordinates
    center_coords = [
        (f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
        for f in rescue_centers
    ]

    pathfinder = RescuePathFinder()
    allocator = ResourceAllocator(
        rescue_centers=center_coords,
        affected_clusters=clusters,
        pathfinder=pathfinder,
    )

    plan = allocator.generate_deployment_plan(request.resources)
    return plan


@app.get("/api/population/{village_id}")
async def get_population_clusters(village_id: str):
    """Get population cluster data for a village."""
    clusters = data_pipeline.load_population_clusters(village_id)
    return {"village_id": village_id, "clusters": clusters}


# =============================================
# Startup Events
# =============================================

@app.on_event("startup")
async def startup_event():
    logger.info("Jal Drishti API starting up...")
    for vid in VILLAGES:
        report = data_pipeline.validate_dataset(vid)
        status = "✓" if report["complete"] else "✗"
        logger.info(f"  {status} {vid}: data {'complete' if report['complete'] else 'incomplete'}")
    logger.info("API ready.")
