"""Single source of truth for the legacy CGI DB password.

Fallback order:
  1) env WHEATOMICS_DB_PASSWORD (set by Apache SetEnv / systemd / wrapper)
  2) /etc/wheatomics_db.conf       (root:www-data 640; recommended for CGI)
  3) app .env at /var/www/FastAPI_backend_Port8000/.env

NOTE: legacy CGI runs under Python 2.7; keep this file syntax-compatible
with BOTH Python 2 and 3 (no annotations, no f-strings, no encoding= kwarg).
"""
import os


def _load():
    v = os.environ.get('WHEATOMICS_DB_PASSWORD')
    if v:
        return v
    candidates = (
        '/etc/wheatomics_db.conf',
        '/var/www/FastAPI_backend_Port8000/.env',
    )
    for p in candidates:
        fh = None
        try:
            fh = open(p, 'r')
            for line in fh:
                line = line.strip()
                if line.startswith('DB_PASSWORD='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
        except (OSError, IOError):
            continue
        finally:
            if fh is not None:
                fh.close()
    return ''


DB_PASSWORD = _load()
