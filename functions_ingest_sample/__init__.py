
# __init__.py – Azure Functions (HTTP trigger) sample for ingesting a document
import logging
import azure.functions as func
import requests
from datetime import datetime
from openai_client import azure_openai_embed
from config import CONFIG

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('DocSpace Ingest Function processed a request.')
    # Expect JSON: { "id": "...", "name": "...", "contentUrl": "Graph file content URL", "lastModified": "..." }
    try:
        data = req.get_json()
    except Exception:
        return func.HttpResponse("Invalid JSON", status_code=400)

    file_id = data.get("id")
    name = data.get("name")
    content_url = data.get("contentUrl")
    last_modified = data.get("lastModified") or datetime.utcnow().isoformat()

    if not (file_id and name and content_url):
        return func.HttpResponse("Missing fields", status_code=400)

    # Download file bytes from Graph (assumes caller passes a pre-authenticated URL or SAS-like link)
    r = requests.get(content_url, timeout=60)
    r.raise_for_status()
    raw = r.content
    # Simple decode; production -> Document Intelligence
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    # Create embedding
    emb = azure_openai_embed(text[:8000])

    # Upsert to Cognitive Search
    import requests, json
    url = f"{CONFIG['SEARCH_ENDPOINT']}/indexes/{CONFIG['SEARCH_INDEX']}/docs/index?api-version=2024-07-01"
    headers = {"Content-Type":"application/json","api-key":CONFIG["SEARCH_API_KEY"]}
    payload = {
        "value":[{
            "@search.action":"mergeOrUpload",
            "id": file_id,
            "name": name,
            "content": text,
            "lastModified": last_modified,
            "views": 0,
            "contentVector": emb
        }]
    }
    rr = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    rr.raise_for_status()

    return func.HttpResponse("ok", status_code=200)
