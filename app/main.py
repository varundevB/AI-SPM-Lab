"""Day 1: a minimal API to learn the request-response cycle."""

from fastapi import FastAPI

app = FastAPI(
    title="SentinelAI",
    description="An AI Security Posture Management learning project.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Confirm that the application can respond to a request."""
    return {"status": "ok"}
