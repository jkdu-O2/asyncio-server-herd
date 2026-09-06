import asyncio
import time
import random
import logging
import statistics
import yaml
import argparse

class LoadTester:
    def __init__(self, config_path="config.yml"):
        with open(config_path, "r") as file:
            self.settings = yaml.safe_load(file)
        
        self.hosts = self.settings["ports"]          # key changed to "ports"
        self.client_count = self.settings["benchmark"]["num_clients"]
        self.duration_sec = self.settings["benchmark"]["test_duration"]
        self.timeout_sec = self.settings["benchmark"]["timeout"]
        
        logging.basicConfig(
            level=getattr(logging, self.settings["logging"]["level"].upper(), logging.INFO),
            filename=self.settings["logging"]["filename"],
            format=self.settings["logging"]["format"]
        )
        self.logger = logging.getLogger("LoadTester")
        self.latency_list = []
        self.request_total = 0
        self.error_count = 0

    def make_location(self):
        lat = random.uniform(-90, 90)
        lng = random.uniform(-180, 180)
        return f"{lat:+.6f}{lng:+.6f}"

    async def send_message(self, server, port, message):
        start_time = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port), timeout=self.timeout_sec
            )
            writer.write(message.encode())
            await writer.drain()
            
            response_data = []
            if "IAMAT" in message:
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout_sec)
                if line:
                    response_data.append(line.decode())
            else:
                empty_lines = 0
                while True:
                    try:
                        line = await asyncio.wait_for(reader.readline(), timeout=self.timeout_sec)
                        if not line:
                            break
                        decoded = line.decode()
                        response_data.append(decoded)
                        if decoded.strip() == "":
                            empty_lines += 1
                            if empty_lines >= 2:
                                break
                        else:
                            empty_lines = 0
                    except asyncio.TimeoutError:
                        break
            
            writer.close()
            await writer.wait_closed()
            latency = time.time() - start_time
            return latency, "".join(response_data).strip()
        except Exception as e:
            self.logger.error(f"Error sending request to {server} on port {port}: {e}")
            return None, None

    async def worker_task(self, worker_id, stop_event):
        while not stop_event.is_set():
            server_name = random.choice(list(self.hosts.keys()))
            port = self.hosts[server_name]
            client_id = f"client{random.randint(1, self.client_count)}"
            
            if random.random() < 0.7:
                location = self.make_location()
                message = f"IAMAT {client_id} {location} {time.time()}\n"
            else:
                radius = random.uniform(1, 50)
                bound = random.randint(1, 20)
                message = f"WHATSAT {client_id} {radius} {bound}\n"

            latency, response = await self.send_message(server_name, port, message)
            if latency is not None:
                self.latency_list.append(latency)
                self.request_total += 1
            else:
                self.error_count += 1
            
            await asyncio.sleep(random.uniform(0.01, 0.1))

    def print_results(self, duration):
        avg_latency = statistics.mean(self.latency_list) if self.latency_list else 0
        max_latency = max(self.latency_list) if self.latency_list else 0
        min_latency = min(self.latency_list) if self.latency_list else 0
        rps = self.request_total / duration if duration > 0 else 0

        results = [
            f"\nBenchmark Results (Duration: {duration:.2f}s):",
            f"Total Requests Sent: {self.request_total}",
            f"Total Errors: {self.error_count}",
            f"Requests Per Second: {rps:.2f}",
            f"Average Latency: {avg_latency:.4f} sec",
            f"Max Latency: {max_latency:.4f} sec",
            f"Min Latency: {min_latency:.4f} sec",
        ]

        for line in results:
            self.logger.info(line)
            print(line)

    async def start_benchmark(self, concurrency=10):
        print(f"Starting benchmark for {self.duration_sec} seconds with {concurrency} workers...")
        stop_event = asyncio.Event()
        workers = [self.worker_task(i, stop_event) for i in range(concurrency)]
        start_time = time.time()
        worker_task = asyncio.gather(*workers)
        await asyncio.sleep(self.duration_sec)
        stop_event.set()
        try:
            await asyncio.wait_for(worker_task, timeout=self.timeout_sec + 1)
        except asyncio.TimeoutError:
            pass
        duration = time.time() - start_time
        self.print_results(duration)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark for Proxy Herd")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent workers")
    args = parser.parse_args()
    tester = LoadTester()
    asyncio.run(tester.start_benchmark(concurrency=args.concurrency))