"""Nautilus Admin UI — operator-facing dashboard and API routes."""

from fastapi import APIRouter


def create_admin_router() -> APIRouter:
    """Return an APIRouter mounted at /admin for operator-facing views."""
    router = APIRouter(prefix="/admin", tags=["admin"])
    return router
