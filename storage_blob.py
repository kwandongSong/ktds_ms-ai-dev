# storage_blob.py (보강)
from typing import Optional
from azure.storage.blob import BlobServiceClient, ContentSettings
from config import CONFIG
import io

def _svc():
    account = CONFIG["AZURE_STORAGE_ACCOUNT"]
    key = CONFIG["AZURE_STORAGE_KEY"]
    container = CONFIG.get("AZURE_STORAGE_CONTAINER", "docspace")
    conn = f"DefaultEndpointsProtocol=https;AccountName={account};AccountKey={key};EndpointSuffix=core.windows.net"
    svc = BlobServiceClient.from_connection_string(conn)
    return svc, svc.get_container_client(container)

def list_blobs_detailed(prefix: str = None):
    _, cc = _svc()
    out = []
    for b in cc.list_blobs(name_starts_with=prefix):
        out.append({
            "name": b.name,
            "size": getattr(b, "size", None),
            "content_type": getattr(b, "content_settings", ContentSettings()).content_type if getattr(b, "content_settings", None) else None,
            "last_modified": getattr(b, "last_modified", None).isoformat() if getattr(b, "last_modified", None) else None,
        })
    return out

def upload_blob(blob_name, data: bytes, overwrite: bool = True,
                content_type: Optional[str] = None, container: Optional[str] = None) -> str:
    account = CONFIG["AZURE_STORAGE_ACCOUNT"]
    key     = CONFIG["AZURE_STORAGE_KEY"]
    svc = BlobServiceClient(account_url=f"https://{account}.blob.core.windows.net", credential=key)

    cont_name = container or CONFIG.get("REPORTS_CONTAINER") or "docspace"
    container_client = svc.get_container_client(cont_name)
    try:
        container_client.create_container()
    except Exception:
        pass

    blob_client = container_client.get_blob_client(blob_name)
    cs = ContentSettings(content_type=content_type) if content_type else None
    blob_client.upload_blob(io.BytesIO(data), overwrite=overwrite,
                            content_settings=cs)
    return f"{cont_name}/{blob_name}"

def download_blob(blob_name: str) -> bytes:
    _, cc = _svc()
    bc = cc.get_blob_client(blob_name)
    return bc.download_blob().readall()

def delete_blob(blob_name: str):
    _, cc = _svc()
    cc.delete_blob(blob_name)
