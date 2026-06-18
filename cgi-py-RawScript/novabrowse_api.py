#!/usr/bin/env python3
import cgi
import json
import sys

sys.path.append("/var/www/novabrowse_service")

from run_novabrowse import run

print("Content-Type: application/json\n")

form = cgi.FieldStorage()

chrom = form.getvalue("chrom")
start = int(form.getvalue("start"))
end = int(form.getvalue("end"))

run_id = run(chrom, start, end)

print(json.dumps({
    "url": f"/novabrowse_results/{run_id}/output.html"
}))
