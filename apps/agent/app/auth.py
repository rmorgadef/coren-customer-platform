"""Auth simple por API key para endpoints administrativos.

Si `ADMIN_API_KEY` no está configurado (dev local), no se exige auth.
Si está configurado, se requiere la cabecera `X-Admin-API-Key` o el
query param `?key=` con el mismo valor.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, Query

from app.config import settings


def require_admin_key(
    x_admin_api_key: Optional[str] = Header(default=None),
    key: Optional[str] = Query(default=None),
) -> None:
    expected = settings.admin_api_key
    if not expected:
        return
    provided = x_admin_api_key or key or ""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="API key inválida o ausente")
