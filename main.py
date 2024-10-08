from fastapi import (
    FastAPI,
    Request,
    Form,
    HTTPException,
    UploadFile,
    File,
    Query,
)
from starlette.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import os
from db import hash_password, verify_password
from pdf import upload_to_gemini, generate_topics
from passlib.context import CryptContext
import logging

# Set up FastAPI
app = FastAPI()

# Add session middleware (from starlette)
app.add_middleware(SessionMiddleware, secret_key="your_secret_key_here")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Mock database connection function
def get_db_connection():
    return psycopg2.connect(
        database="postgres",
        user="postgres.xdvwtpqclkedpktjsrzc",
        password="aOoDlcdghQ39Gkjr",
        host="aws-0-us-east-1.pooler.supabase.com",
    )


# Sign-up route
@app.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    conn = get_db_connection()
    cur = conn.cursor()
    hashed_password = hash_password(password)
    try:
        cur.execute(
            "INSERT INTO authentication (email, username, password) VALUES (%s, %s, %s)",
            (email, username, hashed_password),
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return HTMLResponse(status_code=400, content="Email or Username already exists")
    finally:
        cur.close()
        conn.close()

    return RedirectResponse(url="/login", status_code=302)


# Login route
@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    # Assuming successful authentication

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM authentication WHERE email = %s or username = %s",
            (login, login),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user or not verify_password(password, user["password"]):
        return HTMLResponse(status_code=400, content="Invalid email or password")

    # Store user information in session
    request.session["email"] = user["email"]
    request.session["username"] = user["username"]

    return RedirectResponse(url="/", status_code=302)


# Configure logging
logging.basicConfig(level=logging.INFO)


@app.get("/logout")
def logout(request: Request):
    username = request.session.get("username")  # Get the username from the session
    logging.info(f"Logging out user: {username}")

    # Clear the session
    request.session.clear()  # Clear all session data

    # Redirect to home page
    response = RedirectResponse(url="/")  # Redirect to home page
    logging.info("Session cleared. Redirecting to home page.")
    return response


# Home route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    username = request.session.get("username")
    email = request.session.get("email")  # Fetch the email ID from the session
    return templates.TemplateResponse(
        "index.html", {"request": request, "username": username, "email": email}
    )


# Route to upload PDF and generate topics
@app.post("/upload_pdf/")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    username = request.session.get("username")  # Check if user is logged in
    if not username:
        return JSONResponse(
            content={"error": "You need to be logged in to upload a file."},
            status_code=401,
        )

    temp_dir = Path("./temp_files")
    temp_dir.mkdir(exist_ok=True)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_location = temp_dir / file.filename
    with open(file_location, "wb") as f:
        f.write(await file.read())

    try:
        uploaded_file = upload_to_gemini(file_location, mime_type="application/pdf")
        topics = generate_topics(uploaded_file)
        return {"topics": topics}
    finally:
        os.remove(file_location)  # Clean up the uploaded file


# Subtopic route
@app.get("/subtopic", response_class=HTMLResponse)
async def subtopic(
    request: Request,
    topic: str = Query(...),
    subtopic: str = Query(...),
):
    return templates.TemplateResponse(
        "subtopic.html", {"request": request, "topic": topic, "subtopic": subtopic}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
