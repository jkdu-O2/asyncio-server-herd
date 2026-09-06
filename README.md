```markdown
# Proxy Herd with asyncio

A distributed server herd implementing location propagation and Google Places API queries, built with Python asyncio.

## Features
- Five servers (`Bailey`, `Bona`, `Campbell`, `Clark`, `Jaquez`) communicating over TCP.
- `IAMAT` – client location update, propagated to all servers via flooding.
- `WHATSAT` – query Google Places API for nearby places (radius ≤50 km, ≤20 results).
- Asynchronous event‑driven design using `asyncio`.
- Concurrent benchmark tool to measure RPS and latency.
- Logging of all server activity.

## Requirements
- Python 3.11+
- `aiohttp`, `pyyaml`

## Installation
```bash
pip install -r requirements.txt
```

## Configuration
Edit `config.yml`:
- Replace `api_key` with your Google Places API key (keep quotes).
- Ports are pre‑assigned (10000–10004). Do not change unless instructed.

## Running the Servers
### Linux / macOS
```bash
make run          # starts all five servers in background
make stop         # stops them
make benchmark CONCURRENCY=10   # run load test
```

### Windows
Double‑click `start_all_servers.bat` or run each server manually:
```cmd
python server.py Bailey
python server.py Bona
...
```

Then run benchmark:
```cmd
python benchmark.py --concurrency 10
```

## Testing Manually
```bash
nc localhost 10000
IAMAT client1 +34.068930-118.445127 1621464827.95
WHATSAT client1 10 5
```

## Project Structure
- `server.py` – main server implementation.
- `benchmark.py` – concurrent client for performance testing.
- `config.yml` – ports, neighbours, API key, logging.
- `start_all_servers.bat` – Windows launcher.
- `Makefile` – convenience commands.
- `requirements.txt` – dependencies.

## License
For educational use only.
```
