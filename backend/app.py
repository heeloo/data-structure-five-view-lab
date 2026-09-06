from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Data Structure Five-View Lab API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://heeloo.github.io",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ExecuteRequest(BaseModel):
    source: str = Field(min_length=1, max_length=20000)
    demo_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "five-view-lab-backend"}


@app.post("/api/execute")
def execute(req: ExecuteRequest):
    # Deliberately disabled until the Clang/LLDB runner is isolated with
    # CPU/memory/time limits, filesystem isolation and networking disabled.
    raise HTTPException(
        status_code=501,
        detail="Clang/LLDB sandbox is not enabled yet. Backend connectivity is working.",
    )
