#!/bin/sh
set -e
python -m scripts.migrate
exec python -m worker.run_worker
