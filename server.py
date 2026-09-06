import asyncio
import aiohttp
import time
import sys
import logging
import json
import re
import yaml

PORTS = {
    "Bailey": 10000,
    "Bona": 10001,
    "Campbell": 10002,
    "Clark": 10003,
    "Jaquez": 10004,
}
NEIGHBORS = {
    "Bailey": ["Bona", "Campbell"],
    "Bona": ["Bailey"],
    "Campbell": ["Bailey", "Bona", "Jaquez"],
    "Clark": ["Jaquez", "Bona"],
    "Jaquez": ["Clark", "Campbell"],
}

def load_api_key():
    """Read API key from config.yml, fallback to placeholder if unavailable."""
    try:
        with open("config.yml", "r") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("api_key", "YOUR_API_KEY_HERE")
    except Exception:
        return "YOUR_API_KEY_HERE"

class ApplicationServer:
    def __init__(self, name):
        self.name = name
        self.port = PORTS[name]
        self.neighbors = NEIGHBORS.get(name, [])
        self.all_ports = PORTS
        self.api_key = load_api_key()
        self.client_records = {}
        self.coord_pattern = re.compile(r'^([+-]\d+\.\d+)([+-]\d+\.\d+)$')

        logging.basicConfig(
            level=logging.INFO,
            filename=f"server_{self.name}.log",
            format="%(asctime)s %(levelname)s: %(message)s",
        )
        self.logger = logging.getLogger(self.name)

    def log(self, msg: str, level=logging.INFO):
        self.logger.log(level, msg)

    def parse_location(self, loc: str):
        m = self.coord_pattern.match(loc)
        return m.groups() if m else (None, None)

    @staticmethod
    def collapse_newlines(text: str) -> str:
        return re.sub(r'\n{2,}', '\n', text).rstrip('\n')

    async def broadcast(self, msg: str, exclude: set):
        for nb in self.neighbors:
            if nb in exclude:
                continue
            try:
                self.log(f"Connecting to neighbor {nb}")
                r, w = await asyncio.open_connection('localhost', self.all_ports[nb])
                w.write(msg.encode())
                await w.drain()
                w.close()
                await w.wait_closed()
                self.log(f"Propagated to {nb}: {msg.strip()}")
            except Exception as e:
                self.log(f"Error propagating to {nb}: {e}", level=logging.ERROR)

    async def handle_AT(self, tokens: list, writer):
        if len(tokens) != 6:
            await self.send_error(" ".join(tokens), writer)
            return
        server_id = tokens[1]
        client_id = tokens[3]
        try:
            client_time = float(tokens[5])
        except ValueError:
            await self.send_error(" ".join(tokens), writer)
            return

        if client_id not in self.client_records or client_time > self.client_records[client_id][1]:
            full_msg = " ".join(tokens) + "\n"
            self.client_records[client_id] = (full_msg.strip(), client_time)
            asyncio.create_task(self.broadcast(full_msg, exclude={server_id}))

    async def handle_IAMAT(self, tokens: list, writer):
        if len(tokens) != 4:
            await self.send_error(" ".join(tokens), writer)
            return
        client_id, location, ts_str = tokens[1], tokens[2], tokens[3]
        try:
            client_time = float(ts_str)
        except ValueError:
            await self.send_error(" ".join(tokens), writer)
            return

        now = time.time()
        diff = now - client_time
        response = f"AT {self.name} {diff:+f} {client_id} {location} {ts_str}\n"
        self.log(f"IAMAT from {client_id}: {response.strip()}")

        if client_id not in self.client_records or client_time > self.client_records[client_id][1]:
            self.client_records[client_id] = (response.strip(), client_time)
            asyncio.create_task(self.broadcast(response, exclude=set()))

        writer.write(response.encode())
        await writer.drain()

    async def handle_WHATSAT(self, tokens: list, writer):
        if len(tokens) != 4:
            await self.send_error(" ".join(tokens), writer)
            return
        client_id = tokens[1]
        try:
            radius = float(tokens[2])
            limit = int(tokens[3])
        except ValueError:
            await self.send_error(" ".join(tokens), writer)
            return

        if radius > 50 or limit > 20 or client_id not in self.client_records:
            await self.send_error(" ".join(tokens), writer)
            return

        update, _ = self.client_records[client_id]
        parts = update.split()
        location = parts[4]
        lat, lng = self.parse_location(location)
        if lat is None or lng is None:
            await self.send_error(" ".join(tokens), writer)
            return

        url = "https://places.googleapis.com/v1/places:searchNearby"
        payload = {
            "maxResultCount": limit,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": float(lat), "longitude": float(lng)},
                    "radius": radius * 1000
                }
            }
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "*"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        data["results"] = data.get("results", [])[:limit]
                        json_str = json.dumps(data, indent=4)
                        json_str = self.collapse_newlines(json_str)
                        response = f"{update}\n{json_str}\n\n"
                        writer.write(response.encode())
                        await writer.drain()
                    else:
                        self.log(f"Google API error: {resp.status}", level=logging.ERROR)
                        await self.send_error(" ".join(tokens), writer)
        except Exception as e:
            self.log(f"WHATSAT exception: {e}", level=logging.ERROR)
            await self.send_error(" ".join(tokens), writer)

    async def send_error(self, cmd: str, writer):
        writer.write(f"? {cmd}\n".encode())
        await writer.drain()
        self.log(f"Invalid command: {cmd}", level=logging.WARNING)

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        self.log(f"New connection from {addr}")
        try:
            while not reader.at_eof():
                data = await reader.readline()
                if not data:
                    break
                msg = data.decode().strip()
                self.log(f"Received: {msg} from {addr}")
                if not msg:
                    continue
                parts = msg.split()
                cmd = parts[0]
                if cmd == "AT":
                    await self.handle_AT(parts, writer)
                elif cmd == "IAMAT":
                    await self.handle_IAMAT(parts, writer)
                elif cmd == "WHATSAT":
                    await self.handle_WHATSAT(parts, writer)
                else:
                    await self.send_error(msg, writer)
        except Exception as e:
            self.log(f"Connection error: {e}", level=logging.ERROR)
        finally:
            writer.close()
            await writer.wait_closed()
            self.log(f"Closed connection from {addr}")

    async def run(self):
        server = await asyncio.start_server(self.handle_client, 'localhost', self.port)
        self.log(f"Listening on port {self.port}")
        async with server:
            await server.serve_forever()

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PORTS:
        sys.stderr.write(f"Usage: python3 server.py <name>\nValid names: {', '.join(PORTS.keys())}\n")
        sys.exit(1)
    name = sys.argv[1]
    srv = ApplicationServer(name)
    try:
        asyncio.run(srv.run())
    except KeyboardInterrupt:
        srv.log("Shutting down.")