"""Instagram Unified Login (Meta Graph). No OAuth old Instagram Login flow.

Validates a Meta token against account assignments/permissions and publishes a
locally saved MP4 directly using Meta's resumable Instagram Reels upload.

The token is handled only in Authorization headers, never logged or included in
exceptions. Do not use on an internet-facing instance without secrets-at-rest.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

VERSION = os.environ.get("LIVECLIP_IG_GRAPH_VERSION", "v26.0")
if not re.fullmatch(r"v[0-9]{1,2}\.0", VERSION):
    VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
UPLOAD = f"https://rupload.facebook.com/ig-api-upload/{VERSION}"


class MetaError(RuntimeError):
    pass


def _json(response, step: str):
    """Never print raw Meta errors as they can contain identifiers/secrets."""
    try:
        parsed = response.json()
    except (ValueError, TypeError):
        raise MetaError(f"{step}: resposta inesperada (HTTP {response.status_code}).") from None
    if not isinstance(parsed, dict):
        raise MetaError(f"{step}: formato inesperado (HTTP {response.status_code}).")
    if response.status_code >= 400 or "error" in parsed:
        err = parsed.get("error")
        if not isinstance(err, dict):
            err = {}
        code = err.get("code", "-")
        sub = err.get("error_subcode", "-")
        raise MetaError(f"{step}: Meta HTTP {response.status_code}, codigo {code}, subcodigo {sub}.")
    return parsed


def _request(token: str, method: str, endpoint: str, *, data=None, params=None, timeout=60):
    try:
        response = httpx.request(
            method,
            f"{GRAPH}/{endpoint.lstrip('/')}",
            params=params,
            data=data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            follow_redirects=False,
        )
        return _json(response, endpoint.rsplit("/", 1)[-1])
    except httpx.RequestError:
        raise MetaError("Falha de rede na comunicacao com a Meta.") from None


def inspect(token: str, expected_username: str = "") -> dict:
    """Validate a Meta token without posting; return trusted IG id/name only."""
    accounts = []
    seen = set()
    after = None
    for _ in range(10):
        params = {"fields": "id,username", "limit": 100}
        if after:
            params["after"] = after
        result = _request(token, "GET", "me/assigned_instagram_accounts", params=params, timeout=30)
        rows = result.get("data")
        if not isinstance(rows, list):
            raise MetaError("Lista de contas autorizadas em formato inesperado.")
        accounts.extend(item for item in rows if isinstance(item, dict) and item.get("id"))
        paging = result.get("paging") or {}
        cursors = paging.get("cursors") if isinstance(paging, dict) else {}
        nxt = cursors.get("after") if isinstance(cursors, dict) else None
        if not rows or not nxt:
            break
        if nxt in seen:
            raise MetaError("Paginacao repetida na lista de contas.")
        seen.add(nxt)
        after = nxt
    else:
        raise MetaError("Lista extensa demais; confirme as contas manualmente.")
    wanted = expected_username.strip().lstrip("@").lower()
    matches = [a for a in accounts if a.get("username", "").lower() == wanted] if wanted else accounts
    if not matches:
        raise MetaError("Conta Instagram nao atribuida a este token. Confira o acesso no painel Meta.")
    if len(matches) != 1:
        raise MetaError("Mais de uma conta autorizada; informe --usuario com o @ exato.")
    account = matches[0]
    ig_id = str(account["id"])
    if not re.fullmatch(r"[0-9]{6,25}", ig_id):
        raise MetaError("ID Instagram invalido no retorno da Meta.")
    profile = _request(token, "GET", ig_id, params={"fields": "id,username"}, timeout=30)
    if str(profile.get("id")) != ig_id:
        raise MetaError("O ID da conta nao corresponde ao perfil autorizado.")
    perms = _request(token, "GET", "me/permissions", timeout=30)
    rows = perms.get("data")
    if not isinstance(rows, list):
        raise MetaError("Nao foi possivel confirmar as permissoes do token.")
    granted = {str(a.get("permission")) for a in rows if isinstance(a, dict) and a.get("status") == "granted"}
    if "instagram_content_publish" not in granted or "instagram_basic" not in granted:
        raise MetaError("Falta instagram_basic ou instagram_content_publish no token.")
    return {"id": ig_id, "username": str(profile.get("username", "")).lower(), "permissions_ok": True}


def instagram_upload(acc: dict, path: Path, caption: str, job_id: str = ""):
    """One Reel upload. This is invoked only by the existing posting queue.

    No public URL / Cloudflare Tunnel needed; upload is sent from local disk.
    """
    token = acc.get("token", "")
    ig_id = str(acc.get("user_id", ""))
    if not token or not re.fullmatch(r"[0-9]{6,25}", ig_id):
        raise MetaError("Conta Instagram Unificado desconectada ou ID invalido.")
    path = Path(path)
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise MetaError("Para publicar um Reel, selecione um MP4 existente.")
    size = path.stat().st_size
    if size <= 0 or size > 300 * 1024 * 1024:
        raise MetaError("O MP4 deve ter tamanho entre 1 byte e 300 MB.")
    if not caption.strip():
        caption = "Video"
    # Durable receipt prevents duplicates if the existing posting queue retries
    # after the Meta publish call succeeded but its response was lost.
    receipt = path.with_name("." + path.stem + f".ig_{ig_id}.receipt.json")
    fingerprint = {"file_size": size, "mtime_ns": path.stat().st_mtime_ns}
    if receipt.exists():
        try:
            previous = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise MetaError("Recibo de publicacao ilegivel; confira o Instagram antes de repetir.") from None
        if all(previous.get(k) == v for k, v in fingerprint.items()):
            if previous.get("state") == "posted":
                return previous["media_id"], previous.get("permalink", "")
            if previous.get("state") == "publish_started":
                raise MetaError("Publicacao com resultado incerto: verifique o Instagram antes de repetir.")

    def save_receipt(state, **fields):
        payload = {**fingerprint, "state": state, **fields}
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(receipt)

    # Avoid a new network connection for every 1MB chunk. A Content-Length
    # header keeps the raw upload compatible with rupload's byte protocol.
    container = _request(token, "POST", f"{ig_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable",
        "caption": caption[:2200], "share_to_feed": "true",
    }, timeout=60)
    container_id = str(container.get("id", ""))
    if not re.fullmatch(r"[0-9]{6,25}", container_id):
        raise MetaError("A Meta nao retornou um identificador valido para o video.")
    try:
        def chunks():
            with path.open("rb") as video:
                while True:
                    block = video.read(1024 * 1024)
                    if not block:
                        break
                    yield block
        with httpx.Client(timeout=httpx.Timeout(900, connect=30), follow_redirects=False) as client:
            response = client.post(
                f"{UPLOAD}/{container_id}",
                content=chunks(),
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0", "file_size": str(size),
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                },
            )
        _json(response, "Transferencia do MP4")
    except httpx.RequestError:
        raise MetaError("Falha de rede durante o envio do MP4. Nao foi publicado.") from None

    for _ in range(90):
        status = _request(token, "GET", container_id,
                          params={"fields": "status_code,status"}, timeout=30)
        code = str(status.get("status_code", "")).upper()
        if code in ("FINISHED", "PUBLISHED"):
            break
        if code in ("ERROR", "EXPIRED"):
            raise MetaError(f"A Meta rejeitou o video. Status: {code}.")
        time.sleep(6)
    else:
        raise MetaError("A Meta nao terminou o processamento do Reel. Verifique antes de tentar novamente.")

    # ONLY here does the video become public. Record possible publishing BEFORE
    # sending the request: an ambiguous network failure must never double-post.
    save_receipt("publish_started", container_id=container_id)
    pub = _request(token, "POST", f"{ig_id}/media_publish",
                   data={"creation_id": container_id}, timeout=60)
    media_id = str(pub.get("id", ""))
    if not re.fullmatch(r"[0-9]{6,25}", media_id):
        raise MetaError("Publicacao sem ID de retorno; verifique o Instagram antes de repetir.")
    permalink = ""
    try:
        details = _request(token, "GET", media_id,
                           params={"fields": "permalink"}, timeout=30)
        link = details.get("permalink", "")
        if isinstance(link, str) and link.startswith("https://www.instagram.com/"):
            permalink = link
    except MetaError:
        pass
    save_receipt("posted", container_id=container_id, media_id=media_id,
                 permalink=permalink)
    return media_id, permalink


def instagram_views(acc, media_id: str):
    token = acc.get("token", "")
    try:
        value = _request(token, "GET", f"{media_id}/insights",
                         params={"metric": "views"}, timeout=30)
        data = value.get("data") or []
        if isinstance(data, list) and data:
            item = data[0]
            values = item.get("values") if isinstance(item, dict) else None
            if isinstance(values, list) and values:
                return int(values[0]["value"])
    except (MetaError, ValueError, KeyError, TypeError):
        pass
    return None
