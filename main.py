from fastapi import FastAPI, Request, Response, Cookie
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import os
import json
import secrets
import hashlib
import base64
import uuid
import requests as http_requests
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from datetime import datetime, timedelta
from typing import Optional

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
SCOPES = "https://www.googleapis.com/auth/gmail.readonly"

sessions = {}


def get_session(session_id: Optional[str]) -> dict:
    if session_id and session_id in sessions:
        return sessions[session_id]
    return {}


class ChatRequest(BaseModel):
    message: str


def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def get_email_headers(msg_data, name):
    headers_list = msg_data.get("payload", {}).get("headers", [])
    return next((h["value"] for h in headers_list if h["name"] == name), "")


def fetch_emails(token, query, max_results=15):
    headers = {"Authorization": f"Bearer {token}"}
    msgs = http_requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}&q={query}",
        headers=headers
    ).json()

    emails = []
    for msg in msgs.get("messages", []):
        msg_data = http_requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date",
            headers=headers
        ).json()
        emails.append({
            "sender": get_email_headers(msg_data, "From"),
            "subject": get_email_headers(msg_data, "Subject"),
            "date": get_email_headers(msg_data, "Date"),
            "snippet": msg_data.get("snippet", "")
        })
    return emails


@app.get("/", response_class=HTMLResponse)
def root(request: Request, session_id: Optional[str] = Cookie(default=None)):
    session = get_session(session_id)
    if "token" not in session:
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI Email Assistant</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
        .login-box { background: white; border-radius: 12px; padding: 40px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }
        h1 { font-size: 24px; color: #333; margin-bottom: 10px; }
        p { font-size: 14px; color: #888; margin-bottom: 30px; }
        .login-btn { display: inline-block; padding: 12px 30px; background: #4285f4; color: white; border-radius: 8px; text-decoration: none; font-size: 16px; }
        .login-btn:hover { background: #3367d6; }
        .features { text-align: left; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px; }
        .feature { font-size: 13px; color: #666; margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>AI Email Assistant</h1>
        <p>Connect your Gmail and let AI analyze your emails</p>
        <a href="/auth/login" class="login-btn">Sign in with Google</a>
        <div class="features">
            <div class="feature">📧 Real-time email stats</div>
            <div class="feature">🤖 AI-powered email search</div>
            <div class="feature">💰 Financial reports PDF</div>
            <div class="feature">💬 Chat about your emails</div>
        </div>
    </div>
</body>
</html>
"""
    return open("index.html", encoding="utf-8").read()


@app.get("/auth/login")
def login(response: Response, session_id: Optional[str] = Cookie(default=None)):
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {}

    verifier, challenge = generate_pkce()
    sessions[session_id]["verifier"] = verifier

    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={session_id}"
    )

    redirect = RedirectResponse(url)
    redirect.set_cookie(key="session_id", value=session_id, httponly=True, max_age=2592000)
    return redirect


@app.get("/auth/callback")
def callback(code: str, state: str):
    session_id = state
    if session_id not in sessions:
        sessions[session_id] = {}

    verifier = sessions[session_id].get("verifier")
    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
    )
    tokens = resp.json()
    sessions[session_id]["token"] = tokens.get("access_token")
    sessions[session_id]["refresh_token"] = tokens.get("refresh_token")

    redirect = RedirectResponse("/")
    redirect.set_cookie(key="session_id", value=session_id, httponly=True, max_age=2592000)
    return redirect


@app.get("/auth/logout")
def logout(session_id: Optional[str] = Cookie(default=None)):
    if session_id and session_id in sessions:
        del sessions[session_id]
    redirect = RedirectResponse("/")
    redirect.delete_cookie("session_id")
    return redirect


@app.get("/emails/stats")
def email_stats(session_id: Optional[str] = Cookie(default=None)):
    session = get_session(session_id)
    if "token" not in session:
        return {"error": "Not authenticated. Go to /auth/login first"}

    headers = {"Authorization": f"Bearer {session['token']}"}

    unread = http_requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels/UNREAD",
        headers=headers
    ).json()

    amazon = http_requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=from:amazon.com&maxResults=500",
        headers=headers
    ).json()

    invoices = http_requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=subject:invoice&maxResults=500",
        headers=headers
    ).json()

    return {
        "unread": unread.get("messagesUnread", 0),
        "amazon": len(amazon.get("messages", [])),
        "invoices": len(invoices.get("messages", [])),
        "urgent": 0
    }


@app.post("/chat")
def chat(request: ChatRequest, session_id: Optional[str] = Cookie(default=None)):
    session = get_session(session_id)

    if "token" not in session:
        return {"reply": "Please login first at /auth/login"}

    if "conversation_history" not in session:
        session["conversation_history"] = []

    extract_prompt = f"Extract a Gmail search query from this user message: '{request.message}'. Return ONLY the search query string, nothing else. Examples: 'find emails from Chase' -> 'from:chase.com', 'find bills to pay' -> 'invoice OR bill OR payment', 'what is important today' -> 'is:unread', 'find emails from Holly' -> 'from:Holly'"

    extract_response = model.generate_content(extract_prompt)
    gmail_query = extract_response.text.strip().replace('"', '').replace("'", "")
    print(f"Gmail query: {gmail_query}")

    emails = fetch_emails(session["token"], gmail_query, max_results=15)

    if not emails:
        emails = fetch_emails(session["token"], "is:unread", max_results=15)

    emails_text = "\n---\n".join([
        f"From: {e['sender']}\nSubject: {e['subject']}\nDate: {e['date']}\nPreview: {e['snippet']}"
        for e in emails
    ])

    context = f"Here are emails found for query '{gmail_query}':\n\n{emails_text}"
    full_prompt = f"{context}\n\nAnswer this question: {request.message}"

    history = session["conversation_history"]
    history.append({"role": "user", "parts": [request.message]})
    if len(history) > 20:
        history = history[-20:]

    chat_session = model.start_chat(history=history[:-1])
    response = chat_session.send_message(full_prompt)

    history.append({"role": "model", "parts": [response.text]})
    session["conversation_history"] = history

    return {"reply": response.text}


@app.get("/report/pdf")
def pdf_report(period: str = "week", session_id: Optional[str] = Cookie(default=None)):
    session = get_session(session_id)
    if "token" not in session:
        return {"error": "Not authenticated"}

    now = datetime.now()
    if period == "week":
        date_from = now - timedelta(days=7)
        period_name = "Current Week"
    elif period == "lastweek":
        date_from = now - timedelta(days=14)
        period_name = "Last Week"
    elif period == "month":
        date_from = now - timedelta(days=30)
        period_name = "Current Month"
    else:
        date_from = now - timedelta(days=7)
        period_name = "Current Week"

    date_str = date_from.strftime("%Y/%m/%d")
    queries = ["invoice", "bill", "payment", "statement", "receipt", "charge"]

    all_emails = []
    for query in queries:
        emails = fetch_emails(session["token"], f"{query} after:{date_str}", max_results=5)
        for e in emails:
            entry = f"From: {e['sender']}\nSubject: {e['subject']}\nDate: {e['date']}\nPreview: {e['snippet']}"
            if entry not in all_emails:
                all_emails.append(entry)

    context = "\n---\n".join(all_emails)

    prompt = f"""Analyze these financial emails for the period: {period_name}

{context}

Return ONLY valid JSON without any extra text or markdown:
{{
  "bills": [
    {{"from": "sender name", "subject": "email subject", "amount": "$XX.XX", "due": "due date or N/A", "status": "due or paid"}}
  ],
  "total_due": "$XX.XX",
  "total_paid": "$XX.XX"
}}"""

    response = model.generate_content(prompt)
    text = re.sub(r'```json|```', '', response.text.strip()).strip()

    try:
        data = json.loads(text)
    except:
        data = {"bills": [], "total_due": "N/A", "total_paid": "N/A"}

    filename = f"finance_report_{period}_{session_id or 'guest'}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Financial Report", styles['Title']))
    elements.append(Paragraph(f"Period: {period_name}", styles['Normal']))
    elements.append(Paragraph(f"Generated: {now.strftime('%m/%d/%Y')}", styles['Normal']))
    elements.append(Spacer(1, 20))

    table_data = [["Sender", "Subject", "Amount", "Due Date", "Status"]]
    for bill in data.get("bills", []):
        table_data.append([
            bill.get("from", "")[:30],
            bill.get("subject", "")[:35],
            bill.get("amount", "N/A"),
            bill.get("due", "N/A"),
            bill.get("status", "N/A")
        ])

    if len(table_data) > 1:
        table = Table(table_data, colWidths=[120, 150, 70, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No financial emails found for this period.", styles['Normal']))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Total Due: {data.get('total_due', 'N/A')}", styles['Heading2']))
    elements.append(Paragraph(f"Total Paid: {data.get('total_paid', 'N/A')}", styles['Heading2']))

    doc.build(elements)

    return FileResponse(filename, media_type="application/pdf", filename=filename)