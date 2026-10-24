import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


class Config:
    """
    Central configuration for the EcoTrack Flask application.
    Values can be overridden using environment variables, but sensible
    defaults are provided so the project runs out-of-the-box with a
    standard XAMPP MySQL setup (root user, no password).
    """

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "ecotrack-dev-secret-key-change-in-production")

    # MySQL (XAMPP defaults)
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DB = os.environ.get("MYSQL_DB", "ecotrack")

    # Session
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24  # 1 day, in seconds
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_SAMESITE = "Lax"
