from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import ModelCatalog, Provider, ProviderSecret, User
from ..schemas import ModelOut, ProviderConnectionResult, ProviderCreate, ProviderOut
from ..security import current_user, decrypt_secret, encrypt_secret


router = APIRouter(prefix="/providers", tags=["providers"])
settings = get_settings()


def require_root(user: User) -> None:
    if not user.is_root:
        raise HTTPException(status_code=403, detail="Root access required")


def clean_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Provider URL must include http:// or https://")
    return url


async def discover(kind: str, base_url: str, api_key: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if kind == "ollama":
        endpoint = f"{base_url}/api/tags"
    else:
        endpoint = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        host = urlparse(base_url).hostname or ""
        if settings.containerized and host in {"127.0.0.1", "localhost", "::1"}:
            detail = (
                "127.0.0.1 points to the Agent Forge API container, not your Linux host. "
                "Use host.containers.internal and make Ollama listen on 0.0.0.0:11434 "
                "(OLLAMA_HOST=0.0.0.0:11434)."
            )
        elif host == "host.containers.internal":
            detail = (
                "The Linux host is reachable by name, but Ollama refused the connection. "
                "Ollama probably listens only on 127.0.0.1. Set OLLAMA_HOST=0.0.0.0:11434, "
                "restart Ollama, and test again."
            )
        else:
            detail = f"Could not reach {endpoint}: {exc}"
        raise HTTPException(status_code=502, detail=detail) from exc
    if kind == "ollama":
        return sorted({item.get("name") for item in payload.get("models", []) if item.get("name")})
    return sorted({item.get("id") for item in payload.get("data", []) if item.get("id")})


def provider_dict(provider: Provider, db: Session) -> dict:
    count = db.scalar(select(func.count()).select_from(ModelCatalog).where(ModelCatalog.provider_id == provider.id)) or 0
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    return {
        "id": provider.id, "name": provider.name, "kind": provider.kind,
        "base_url": provider.base_url, "enabled": provider.enabled,
        "model_count": count, "has_api_key": secret is not None,
    }


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    return [provider_dict(provider, db) for provider in db.scalars(select(Provider).order_by(Provider.name))]


@router.post("", response_model=ProviderOut, status_code=201)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    require_root(user)
    data = payload.model_dump(exclude={"api_key"})
    data["base_url"] = clean_url(payload.base_url)
    provider = Provider(**data, created_by=user.id)
    db.add(provider)
    db.flush()
    if payload.api_key:
        db.add(ProviderSecret(provider_id=provider.id, encrypted_value=encrypt_secret(payload.api_key)))
    db.commit()
    db.refresh(provider)
    return provider_dict(provider, db)


@router.post("/test", response_model=ProviderConnectionResult)
async def test_provider(payload: ProviderCreate, user: User = Depends(current_user)) -> ProviderConnectionResult:
    require_root(user)
    models = await discover(payload.kind, clean_url(payload.base_url), payload.api_key)
    return ProviderConnectionResult(ok=True, message=f"Connected; discovered {len(models)} models", models=models)


@router.post("/{provider_id}/connect", response_model=ProviderConnectionResult)
async def connect_provider(provider_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> ProviderConnectionResult:
    require_root(user)
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    api_key = decrypt_secret(secret.encrypted_value) if secret else None
    models = await discover(provider.kind, provider.base_url, api_key)
    existing = {model.model_id: model for model in db.scalars(select(ModelCatalog).where(ModelCatalog.provider_id == provider.id))}
    for model_id in models:
        if model_id in existing:
            existing[model_id].enabled = True
        else:
            db.add(ModelCatalog(provider_id=provider.id, model_id=model_id, display_name=model_id, capabilities={}))
    for model_id, model in existing.items():
        if model_id not in models:
            model.enabled = False
    db.commit()
    return ProviderConnectionResult(ok=True, message=f"Connected; synchronized {len(models)} models", models=models)


@router.get("/{provider_id}/models", response_model=list[ModelOut])
def list_models(provider_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[ModelCatalog]:
    if not db.get(Provider, provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    return list(db.scalars(select(ModelCatalog).where(ModelCatalog.provider_id == provider_id, ModelCatalog.enabled.is_(True)).order_by(ModelCatalog.display_name)))


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    require_root(user)
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    db.delete(provider)
    db.commit()
