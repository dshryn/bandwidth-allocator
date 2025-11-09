IFACE=${1:-eth0}
set -e
tc filter del dev $IFACE parent ffff: || true
tc qdisc del dev $IFACE ingress || true
tc qdisc del dev ifb0 root || true
ip link set dev ifb0 down || true
ip link del ifb0 || true
echo "IFB cleared for $IFACE"
