from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app import schemas

app = FastAPI(title="ECFA Tariff Optimizer V2")

# Mount frontend static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/tariff-guide")
async def tariff_guide():
    return FileResponse("frontend/tariff-guide.html")

@app.get("/legal-sources")
async def legal_sources():
    return FileResponse("frontend/legal-sources.html")

@app.get("/changelog")
async def changelog():
    return FileResponse("frontend/changelog.html")
