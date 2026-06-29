from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    TelegramBotConfigCreateRequest,
    TelegramBotConfigUpdateRequest,
    TelegramBotConfigView,
)


@dataclass(frozen=True)
class AppTelegramBotsRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
    remove_runtime_env_values: Callable[[set[str]], Any]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_telegram_bots_router(deps: AppTelegramBotsRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-telegram-bots"])

    @router.get("/api/app/telegram-bots", response_model=list[TelegramBotConfigView])
    async def list_telegram_bot_configs(authorization: Optional[str] = Header(default=None)) -> list[TelegramBotConfigView]:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        return [TelegramBotConfigView(**item) for item in bridge.list_telegram_bot_configs()]

    @router.post("/api/app/telegram-bots", response_model=TelegramBotConfigView)
    async def create_telegram_bot_config(
        request: TelegramBotConfigCreateRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> TelegramBotConfigView:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        _check_telegram_bot_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        try:
            return TelegramBotConfigView(**bridge.create_telegram_bot_config(label=request.label, bot_token=request.bot_token))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/app/telegram-bots/{bot_config_id}", response_model=TelegramBotConfigView)
    async def update_telegram_bot_config(
        bot_config_id: str,
        request: TelegramBotConfigUpdateRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> TelegramBotConfigView:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        _check_telegram_bot_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        try:
            item = bridge.update_telegram_bot_config(
                bot_config_id,
                label=request.label,
                bot_token=request.bot_token,
                is_default=request.is_default,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Telegram bot config not found") from exc
        return TelegramBotConfigView(**item)

    @router.delete("/api/app/telegram-bots/{bot_config_id}")
    async def delete_telegram_bot_config(
        bot_config_id: str,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        _check_telegram_bot_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        try:
            result = bridge.delete_telegram_bot_config(bot_config_id)
            if not bridge.list_telegram_bot_configs():
                deps.remove_runtime_env_values({"TELEGRAM_BOT_TOKEN", "EMPLOAI_TELEGRAM_BOT_TOKENS_JSON"})
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("EMPLOAI_TELEGRAM_BOT_TOKENS_JSON", None)
                os.environ["ALLOWED_USER_IDS"] = ""
                result["cleared_telegram_setup"] = True
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Telegram bot config not found") from exc

    return router


def _ensure_local_app_backend(deps: AppTelegramBotsRouterDeps, auth: Dict[str, Any]) -> None:
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="Telegram bot configuration must run on the local desktop backend")


def _check_telegram_bot_rate_limit(
    deps: AppTelegramBotsRouterDeps,
    http_request: Request,
    auth: Dict[str, Any],
) -> None:
    deps.check_rate_limit(
        http_request,
        email=str(auth["user_id"]),
        action="telegram_bot_config",
        max_attempts=deps.rate_limit_max_attempts,
    )
