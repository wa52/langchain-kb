from typing import Annotated

from fastapi import Depends, HTTPException

from src.resources import ResourceManager


def get_rm() -> ResourceManager:
    rm = ResourceManager.get_instance()
    if not rm.is_ready():
        raise HTTPException(status_code=503, detail="ResourceManager not ready")
    return rm


RmDep = Annotated[ResourceManager, Depends(get_rm)]
