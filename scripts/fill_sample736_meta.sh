#!/bin/bash
# Convert sample736.txt → 3 sample_meta JSON files
# Run on the server: /var/www/FastAPI_backend_Port8000/

TXT="/var/www/html/variants/sample736.txt"
JSON_DIR="app/services/data/sample_meta"

if [ ! -f "$TXT" ]; then
    echo "ERROR: $TXT not found"
    exit 1
fi

python3 scripts/convert_sample736.py "$TXT" > /tmp/sample736_out.json
N=$(python3 -c "import json; d=json.load(open('/tmp/sample736_out.json')); print(len(d['samples']))")
echo "Parsed $N samples"

# Copy to all 3 dataset keys
for KEY in Tetra_wheat_sample736_InDel Tetra_wheat_sample736_SNP Tetra_wheat_sample736_SV; do
    cp /tmp/sample736_out.json "$JSON_DIR/$KEY.json"
    echo "  → $JSON_DIR/$KEY.json"
done

rm /tmp/sample736_out.json
echo "Done. Restart uvicorn to pick up changes."
