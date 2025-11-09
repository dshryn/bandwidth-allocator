#!/bin/bash
# scripts/setup_ifb.sh
# Usage: sudo bash setup_ifb.sh <iface>
IFACE=${1:-eth0}
set -e
modprobe ifb || true
ip link add ifb0 type ifb || true
ip link set dev ifb0 up
tc qdisc add dev $IFACE ingress || true
tc filter add dev $IFACE parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0 || true
echo "IFB set up for $IFACE"


