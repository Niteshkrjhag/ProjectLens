"""Run the backend API with ``python -m projectlens``."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("projectlens.api:app", host="127.0.0.1", port=8000, reload=False)
