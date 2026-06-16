# AI Email Assistant

An AI-powered email assistant that connects to Gmail and uses Gemini AI to analyze emails and answer questions.

## Features

- Gmail OAuth integration — secure login with Google
- Real-time email statistics — unread, Amazon, invoices
- AI chat — ask questions about your emails in natural language
- Email search — find emails by sender, topic, or keyword
- Financial reports — PDF reports with bills and payments
- Conversation memory — AI remembers context of the conversation
- Docker support — easy deployment with Docker

## Tech Stack

- **Backend:** Python, FastAPI
- **AI:** Google Gemini API
- **Email:** Gmail API, OAuth 2.0
- **Frontend:** HTML, CSS, JavaScript
- **DevOps:** Docker, Docker Compose

## How to Run

1. Clone the repository
2. Get Gmail API credentials from Google Cloud Console
3. Get Gemini API key from Google AI Studio
4. Create `.env` file with your `GEMINI_API_KEY`
5. Add `credentials.json` from Google Cloud Console
6. Run with Docker:

```bash
docker compose up --build
```

7. Open `http://localhost:8000`
8. Login with your Google account
