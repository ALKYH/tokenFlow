from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import FRONTEND_ORIGINS
from .db.session import create_db_and_tables, ensure_runtime_schema
from . import models  # noqa: F401
from .routers import auth as auth_router
from .routers import inbox as inbox_router
from .routers import plugins as plugins_router
from .routers import profile as profile_router
from .routers import routing as routing_router
from .routers import runtime as runtime_router
from .routers import workspaces as workspaces_router
from .seed import seed_initial_data

app = FastAPI(title='tokenFlow Auth')

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ['http://localhost:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router.router)
app.include_router(auth_router.compat_router)
app.include_router(profile_router.router)
app.include_router(plugins_router.router)
app.include_router(workspaces_router.router)
app.include_router(routing_router.router)
app.include_router(inbox_router.router)
app.include_router(runtime_router.router)


@app.on_event('startup')
async def on_startup():
    await create_db_and_tables()
    await ensure_runtime_schema()
    await seed_initial_data()


@app.get('/health')
async def health():
    return {'ok': True}
