import os


class Config:
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    CLOUDWATCH_NAMESPACE = os.environ.get("CLOUDWATCH_NAMESPACE", "AuthService")
    MAX_FAILED_ATTEMPTS = int(os.environ.get("MAX_FAILED_ATTEMPTS", "5"))
    LOCKOUT_DURATION_SECONDS = int(os.environ.get("LOCKOUT_DURATION_SECONDS", "300"))
    SESSION_TOKEN_TTL_SECONDS = int(os.environ.get("SESSION_TOKEN_TTL_SECONDS", "3600"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")