from datetime import datetime, timedelta
from pathlib import Path


DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def default_range(now=None):
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    start = now.replace(second=0, microsecond=0) - timedelta(days=7)
    return start, now


def format_datetime(value):
    return value.strftime(DATETIME_FORMAT)


def parse_datetime(value):
    text = str(value or "").strip()
    for pattern in (DATETIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("Use date and time as YYYY-MM-DD HH:MM.")


def validate_report_options(from_value, to_value, bullet_value, folder_value):
    start = parse_datetime(from_value)
    end = parse_datetime(to_value)
    if start >= end:
        raise ValueError("The start date and time must be earlier than the end date and time.")

    try:
        bullet_limit = int(str(bullet_value).strip())
    except ValueError:
        raise ValueError("Bullet points per section must be an integer.")
    if bullet_limit < 1:
        raise ValueError("Bullet points per section must be at least 1.")

    folder = Path(str(folder_value or "").strip())
    if not str(folder):
        raise ValueError("Choose a destination folder.")
    if not folder.exists() or not folder.is_dir():
        raise ValueError("Choose a valid destination folder.")

    return {
        "start": start,
        "end": end,
        "bullet_limit": bullet_limit,
        "folder": folder,
    }
