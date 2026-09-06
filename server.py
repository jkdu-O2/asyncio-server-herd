import asyncio
import aiohttp
import time
import sys
import logging
import json
import re
import yaml

DEFAULT_PORTS = {
    "Bailey": 10000,
    "Bona": 10001,
    "Campbell": 10002,
    "Clark": 10003,
    "Jaquez": 10004,
}
DEFAULT_NEIGHBORS = {
    "Bailey": ["Bona", "Campbell"],
    "Bona": ["Bailey"],
    "Campbell": ["Bailey", "Bona", "Jaquez"],
    "Clark": ["Jaquez", "Bona"],
    "Jaquez": ["Clark", "Campbell"],
}

def load_config():
    """Load ports, neighbors, and API key from config.yml.
       Fall back to defaults if the file or keys are missing."""
    try:
        with open("config.yml", "r") as f:
            cfg = yaml.safe_load(f)
        ports = cfg.get("ports", DEFAULT_PORTS)
        neighbors = cfg.get("neighbors", DEFAULT_NEIGHBORS)
        api_key = cfg.get("api_key", "YOUR_API_KEY_HERE")
        return ports, neighbors, api_key
    except Exception:
        return DEFAULT_PORTS, DEFAULT_NEIGHBORS, "YOUR_API_KEY_HERE"

class ApplicationServer:
    def __init__(self, name):
        self.name = name
        self.ports, self.neighbors_cfg, self.api_key = load_config()
        self.port = self.ports[name]
        self.neighbors = self.neighbors_cfg.get(name, [])
        self.all_ports = self.ports
        self.client_records = {}
        self.coord_pattern = re.compile(r'^([+-]\d+\.\d+)([+-]\d+\.\d+)$')
        self.session = None  # shared aiohttp session

        logging.basicConfig(
            level=logging.INFO,
            filename=f"server_{self.name}.log",
            format="%(asctime)s %(levelname)s: %(message)s",
        )
        self.logger = logging.getLogger(self.name)

    async def get_session(self):
        """Return a persistent aiohttp session, creating it on first use."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def log(self, msg: str, level=logging.INFO):
        self.logger.log(level, msg)

    def parse_location(self, loc: str):
        m = self.coord_pattern.match(loc)
        return m.groups() if m else (None, None)

    @staticmethod
    def collapse_newlines(text: str) -> str:
        return re.sub(r'\n{2,}', '\n', text).rstrip('\n')

    async def send_to_neighbor(self, nb, msg):
        """Send a message to a single neighbor with a timeout."""
        try:
            self.log(f"Connecting to neighbor {nb}")
            # Use a timeout for connection
            r, w = await asyncio.wait_for(
                asyncio.open_connection('localhost', self.all_ports[nb]),
                timeout=2.0
            )
            w.write(msg.encode())
            await w.drain()
            w.close()
            await w.wait_closed()
            self.log(f"Propagated to {nb}: {msg.strip()}")
        except Exception as e:
            self.log(f"Error propagating to {nb}: {e}", level=logging.ERROR)

    async def broadcast(self, msg: str, exclude: set):
        """Propagate message concurrently to all neighbors not in exclude."""
        tasks = [
            self.send_to_neighbor(nb, msg)
            for nb in self.neighbors
            if nb not in exclude
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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

        # Validate radius and limit properly
        if radius < 0 or radius > 50 or limit <= 0 or limit > 20 or client_id not in self.client_records:
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
            session = await self.get_session()
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
        try:
            async with server:
                await server.serve_forever()
        finally:
            await self.close_session()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(f"Usage: python3 server.py <name>\n")
        sys.exit(1)
    name = sys.argv[1]
    # Validate name against loaded ports
    ports, _, _ = load_config()
    if name not in ports:
        sys.stderr.write(f"Invalid server name. Valid names: {', '.join(ports.keys())}\n")
        sys.exit(1)
    srv = ApplicationServer(name)
    try:
        asyncio.run(srv.run())
    except KeyboardInterrupt:
        srv.log("Shutting down.")
