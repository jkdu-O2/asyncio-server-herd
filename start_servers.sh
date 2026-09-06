#!/bin/bash
# Start all five servers in background
python3 server.py Bailey &
python3 server.py Bona &
python3 server.py Campbell &
python3 server.py Clark &
python3 server.py Jaquez &
echo "All servers started."