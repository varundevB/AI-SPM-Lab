"""AI-SPM-Lab API application."""

from fastapi import FastAPI

app = FastAPI(
    title="AI-SPM-Lab",
    description="AI Security Posture Management for AI applications.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Confirm that the application can respond to a request."""
    return {"status": "ok"}
