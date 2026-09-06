# Asyncio Application Server Herd

A distributed server herd implementing location propagation and Google Places API queries, built with Python asyncio.

## Features
- Five servers (`Bailey`, `Bona`, `Campbell`, `Clark`, `Jaquez`) communicating over TCP.
- `IAMAT` – client location update, propagated to all servers via flooding.
- `WHATSAT` – query Google Places API for nearby places (radius ≤50 km, ≤20 results).
- Asynchronous event-driven design using `asyncio`.
- Concurrent benchmark tool to measure RPS and latency.
- Logging of all server activity.
- USENIX-style report evaluating asyncio for this workload.

## Requirements
- Python 3.11+
- `aiohttp`, `pyyaml`

## Installation
```bash
pip install -r requirements.txt
```

## Configuration
1. Obtain a Google Places API key from [Google Cloud Console](https://console.cloud.google.com/).
2. Edit `config.yml`:
   - Set your API key in the `api_key` field.
   - Modify `ports` and `neighbors` if you need to change the server topology (defaults are provided).
3. Do not commit your real API key to version control.

## Running the Servers
### Linux / macOS
```bash
make run          # starts all five servers in background
make stop         # stops them
make benchmark CONCURRENCY=10   # run load test
```

### Windows
Run each server manually in separate terminals:
```cmd
python server.py Bailey
python server.py Bona
...
```
Then run the benchmark:
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
- `config.yml` – ports, neighbors, API key placeholder, logging.
- `REPORT.md` – research report on asyncio suitability.
- `report.pdf` – PDF version of the report.
- `start_all_servers.bat` – Windows launcher (optional).
- `Makefile` – convenience commands for Linux/macOS.
- `requirements.txt` – dependencies.

## Performance Results
From the benchmark (50 concurrent workers, 5 seconds):
- Total requests: 188
- Errors: 0
- Requests per second: 27.93
- Average latency: 1.54 s
- IAMAT‑only throughput: >500 RPS (min latency 0.002 s)

See the report for detailed analysis.

## License
For educational use only.
