#!/bin/bash
# Run server on host A (the target machine): iperf3 -s
# On client (other machine) run test:
# ./test_iperf.sh <server_ip> <duration_seconds>
SERVER=${1}
DURATION=${2:-10}
if [[ -z "$SERVER" ]]; then
  echo "Usage: $0 <server_ip> [duration_seconds]"
  exit 1
fi
iperf3 -c $SERVER -t $DURATION -P 4
