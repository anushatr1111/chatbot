# === main.py (FastAPI backend) ===

from fastapi import FastAPI, Request, Body, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from pydantic import BaseModel
import os
import json
import uuid
import dateparser
import re
from typing import Optional

from calendar_service import CalendarService
from dotenv import load_dotenv
load_dotenv()
print("Loaded creds:", bool(os.environ.get("GOOGLE_OAUTH_CREDENTIALS")))

app = FastAPI(title="Google Calendar Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCOPES = ['https://www.googleapis.com/auth/calendar']
REDIRECT_URI = 'http://localhost:8000/oauth2callback'

user_tokens = {}
chat_sessions = {}

@app.get("/")
async def home():
    return {"message": "Welcome to the Google Calendar Booking API"}

import tempfile
CLIENT_SECRET_JSON = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
if not CLIENT_SECRET_JSON:
    raise RuntimeError("Missing GOOGLE_OAUTH_CREDENTIALS environment variable")

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
    temp_file.write(CLIENT_SECRET_JSON)
    CLIENT_SECRET_FILE = temp_file.name

@app.get("/auth")
async def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    state = str(uuid.uuid4())
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state
    )
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code)

    creds = flow.credentials
    user_tokens[state] = creds.to_json()

    streamlit_url = f"http://localhost:8501/?user_id={state}"
    return RedirectResponse(streamlit_url)

@app.post("/link_session")
async def link_session(request: dict):
    session_id = request.get("session_id")
    user_id = request.get("user_id")

    if user_id in user_tokens:
        user_tokens[session_id] = user_tokens[user_id]
        print(f"[DEBUG] Linked session {session_id} with user {user_id}")
        return {"success": True, "message": "Session linked successfully"}
    else:
        return {"success": False, "message": "User not authenticated"}

@app.get("/auth_status")
async def auth_status(session_id: str = None):
    if session_id and session_id in user_tokens:
        return {"authenticated": True, "session_id": session_id}
    if user_tokens:
        return {"authenticated": True, "available_users": list(user_tokens.keys())}
    return {"authenticated": False}

@app.get("/calendar/events")
async def list_events(user_id: str):
    if user_id not in user_tokens:
        return {"error": "User not authorized. Go to /auth to connect."}

    creds = Credentials.from_authorized_user_info(
        json.loads(user_tokens[user_id]), scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    events_result = service.events().list(
        calendarId='primary',
        maxResults=5,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    return {"events": events}

@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    chat_sessions.pop(session_id, None)
    user_tokens.pop(session_id, None)
    return {"message": "Session reset"}
