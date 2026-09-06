PYTHON_CMD = python3
PIP_CMD = $(PYTHON_CMD) -m pip
SERVER_FILE = server.py
BENCH_FILE = benchmark.py
START_SH = ./start_servers.sh
STOP_SH = ./stop_servers.sh
PID_PATH = servers.pid

.PHONY: all install run stop benchmark clean help

all: help

install:
	$(PIP_CMD) install -r requirements.txt

run:
	@echo "Starting servers..."
	@$(START_SH)

stop:
	@echo "Stopping servers..."
	@$(STOP_SH)

benchmark:
	$(PYTHON_CMD) $(BENCH_FILE) --concurrency $(or $(CONCURRENCY),10)

clean:
	rm -f *.log *.out $(PID_PATH)
	@echo "Cleaned up logs and PID files."

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'