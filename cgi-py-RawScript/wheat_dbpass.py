"""Single source of truth for the legacy CGI DB password.

Fallback order:
  1) env WHEATOMICS_DB_PASSWORD (set by Apache SetEnv / systemd / wrapper)
  2) app .env at /var/www/FastAPI_backend_Port8000/.env (DB_PASSWORD= line)

CGI scripts import this module instead of hardcoding credentials:
    passwd=__import__('wheat_dbpass').DB_PASSWORD
"""
import os


def _load() -> str:
    v = os.environ.get('WHEATOMICS_DB_PASSWORD')
    if v:
        return v
    candidates = (
        '/var/www/FastAPI_backend_Port8000/.env',
    )
    for p in candidates:
        try:
            with open(p, encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('DB_PASSWORD='):
                        return line.split('=', 1)[1].strip().strip('\"').strip("'")
        except OSError:
            continue
    return ''


DB_PASSWORD = _load()
