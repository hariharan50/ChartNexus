RUN THE BACKEND
RUNNING ON 8000
uv run uvicorn marketcompass.entrypoints.main_api:create_app --factory --reload --port 8000 

RUN THE FRONTEND

pnpm run dev
 ➜  Local:   http://localhost:5173/

