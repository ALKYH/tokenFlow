from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/tokenflow')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))
FRONTEND_ORIGINS = [o.strip() for o in os.environ.get('FRONTEND_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
TOKENFLOW_STORAGE_DIR = os.environ.get('TOKENFLOW_STORAGE_DIR', './storage')
