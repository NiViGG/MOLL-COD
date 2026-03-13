"""Entry point."""
import uvicorn
from api import app
from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
