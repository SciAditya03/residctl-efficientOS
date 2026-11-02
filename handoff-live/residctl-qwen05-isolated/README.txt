# residctl Local Benchmark Dashboard

## Install
Copy `dashboard.py` into the `residctl-qwen05-isolated` directory, beside `live_compare.py`.

## Run
In WSL Ubuntu:
```bash
cd ~/projects/residctl/handoff-live/residctl-qwen05-isolated
sudo -v
python3 dashboard.py
```
Keep this terminal open and visit http://localhost:8000 in your browser.

The server binds only to 127.0.0.1. It runs as your normal user; only the benchmark subprocess uses `sudo -n`. Do not expose the port to your LAN or the internet. The dashboard uses Python's standard library; no pip packages are required.

The model must already have been downloaded and verified with `bash download_model.sh`. Results are saved by the existing runner under `results/`.
