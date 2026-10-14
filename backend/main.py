from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.database import initialize_database
from app.routers import log_router, simulation_router, user_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="Edge AI Access Control API",
    version="0.2.0",
    lifespan=lifespan,
)

# Configurare CORS (obligatoriu ca să se poată conecta aplicația frontend de pe telefon sau browser)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Includerea routerelor pe 3 straturi
app.include_router(user_router.router)
app.include_router(log_router.router)
app.include_router(simulation_router.router)

@app.get("/")
def root():
    return {"message": "Edge AI Access Control API is running successfully!"}