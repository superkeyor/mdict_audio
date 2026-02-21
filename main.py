import os
import re
from contextlib import asynccontextmanager
from typing import Tuple, Optional
from fastapi import FastAPI, HTTPException, Security, Depends, Query
from fastapi.security import APIKeyHeader
from fastapi.responses import Response
from mdict_query_r.query import Querier, Dictionary

"""
MDict Audio API
----------------
A high-performance API to serve audio files from MDict (.mdx/.mdd) dictionaries.

USAGE:
1. Header Auth (cURL):
   curl -H "X-API-Key: your_key" http://localhost:8000/audio/apple --output apple.mp3

2. URL Auth (Browser):
   http://localhost:8000/audio/apple?key=your_key

3. Python Auth:
   requests.get("http://localhost:8000/audio/apple", headers={"X-API-Key": "your_key"})
"""

# Hardcoded paths for the embedded Docker dictionary files
# This is a homebrew merged dict with vocabulary.com, webster, and longman American pronunciations
MDX_PATH = "/app/dict/Vocabulary Webster Longman Dict.mdx"
MDD_PATH = "/app/dict/Vocabulary Webster Longman Dict.mdd"

# Setup Header Authentication (X-API-Key)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Global holders for dictionary engines
querier_mdx = None
querier_mdd = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the MDict engines when the container starts."""
    global querier_mdx, querier_mdd

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("FATAL: API_KEY environment variable is not set. System halted.")
    else:
        print(f"STARTUP: API_KEY loaded successfully (starts with: '{api_key[:4]}...')")

    if os.path.exists(MDX_PATH) and os.path.exists(MDD_PATH):
        print(f"LOADING DICTIONARY: {MDX_PATH}")
        querier_mdx = Querier([Dictionary('text', MDX_PATH)])
        querier_mdd = Querier([Dictionary('audio', MDD_PATH)])
        print("STARTUP: Dictionary engines initialized successfully.")
    else:
        print("CRITICAL: Dictionary files missing in /app/dict/")

    yield

    # Shutdown: nothing to clean up for these engines, but hook is here if needed
    print("SHUTDOWN: Application shutting down.")


app = FastAPI(title="MDict Audio API", lifespan=lifespan)


def get_api_key(
    header_key: Optional[str] = Security(api_key_header),
    query_key: Optional[str] = Query(None, alias="key")
):
    """
    Validates the API Key. Checks the HTTP Header 'X-API-Key' first,
    then falls back to the URL parameter '?key='.
    """
    api_key = os.getenv("API_KEY")  # Read fresh at request time
    token = header_key or query_key

    if not token or token != api_key:
        # Avoid logging the full token for security; show only a hint
        hint = token[:4] + "..." if token and len(token) > 4 else repr(token)
        print(f"AUTH FAILURE: Received token hint '{hint}', expected key starting with '{api_key[:4] if api_key else None}...'")
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")

    return token


def extract_audio_and_ext(word: str, q_mdx: Querier, q_mdd: Querier) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Internal logic to link MDX text records to MDD binary audio records.
    """
    # 1. Query MDX for the pointer (HTML)
    records = q_mdx.query(word, ignore_case=True)
    if not records:
        print(f"NOT FOUND: Word '{word}' not in MDX.")
        return None, None

    mdx_data = records[0].entry.data

    # 2. Extract path and extension (mp3, wav, etc.) from href="sound://..."
    match = re.search(r'href="(sound://[^"]+\.(mp3|spx|wav|ogg))"', mdx_data, re.IGNORECASE)
    if not match:
        print(f"PARSE ERROR: No audio link in HTML for '{word}'. Content: {repr(mdx_data)}")
        return None, None

    raw_path = match.group(1)
    ext = match.group(2).lower()

    # 3. Format the key for MDD lookup
    # Standardizes paths to Windows-style backslashes (e.g., \voc\D\file.mp3)
    clean_path = re.sub(r'^sound:(//)?', '', raw_path, flags=re.IGNORECASE)
    mdd_key = "\\" + clean_path.replace("/", "\\")
    mdd_key = re.sub(r'\\+', r'\\', mdd_key)

    print(f"MDD LOOKUP: Word='{word}' -> Searching Key={repr(mdd_key)}")

    # 4. Extract binary data (ignore_case=False bypasses the Rust backslash bug)
    audio_records = q_mdd.query(mdd_key, ignore_case=False)

    # Fallback retry without leading backslash (some dictionaries index differently)
    if not audio_records:
        mdd_key_alt = mdd_key.lstrip("\\")
        print(f"MDD FALLBACK: Retrying with key={repr(mdd_key_alt)}")
        audio_records = q_mdd.query(mdd_key_alt, ignore_case=False)

    if not audio_records:
        print(f"MDD FAILURE: Key '{mdd_key}' not found in .mdd file.")
        return None, None

    return audio_records[0].entry.data, ext


@app.get("/audio/{word}")
def get_word_audio(word: str, api_key: str = Depends(get_api_key)):
    """
    Main endpoint to retrieve audio files.
    Returns binary audio data with the correct Content-Type header.
    """
    if not querier_mdx or not querier_mdd:
        raise HTTPException(status_code=500, detail="Dictionary engines not initialized.")

    audio_bytes, ext = extract_audio_and_ext(word, querier_mdx, querier_mdd)

    if not audio_bytes or not ext:
        raise HTTPException(status_code=404, detail=f"No audio available for word: {word}")

    mime_types = {
        'mp3': 'audio/mpeg',
        'spx': 'audio/speex',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg'
    }

    media_type = mime_types.get(ext, 'application/octet-stream')
    return Response(content=audio_bytes, media_type=media_type)




import logging

class RedactKeyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                re.sub(r'(\?key=)[^\s"]+', r'\1[REDACTED]', arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True

# Attach filter to Uvicorn's access logger
logging.getLogger("uvicorn.access").addFilter(RedactKeyFilter())