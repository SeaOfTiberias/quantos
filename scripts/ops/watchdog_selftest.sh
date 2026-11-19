#!/bin/sh
# Job watchdog self-test (docs/EXECUTION_PLAN_2026-11-19.md, E1 "done when"), on the VM.
#
#   sh scripts/ops/watchdog_selftest.sh start   # installs a throwaway unit that hangs, starts it
#   sh scripts/ops/watchdog_selftest.sh clean   # removes it; the next watchdog run sends "cleared"
#
# The test unit sleeps for an hour with a 5-minute start timeout, like a job stuck on a socket.
# systemd kills it at 5 minutes (Result=timeout), and the next watchdog run (every 15 minutes,
# 08:30-16:15 IST on weekdays) must Telegram "FAILED quantos-watchdog-selftest". Its timer is
# enabled only so the watchdog lists it; its calendar never fires. Touches no other unit.
set -e
U=/etc/systemd/system/quantos-watchdog-selftest
case "$1" in
start)
  sudo tee $U.service >/dev/null <<'EOF'
[Unit]
Description=QuantOS watchdog self-test (hangs on purpose; remove with watchdog_selftest.sh clean)
[Service]
Type=oneshot
ExecStart=/bin/sleep 3600
TimeoutStartSec=5min
EOF
  sudo tee $U.timer >/dev/null <<'EOF'
[Unit]
Description=QuantOS watchdog self-test timer (never fires)
[Timer]
OnCalendar=2099-01-01 00:00:00
[Install]
WantedBy=timers.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable quantos-watchdog-selftest.timer
  sudo systemctl start --no-block quantos-watchdog-selftest.service
  echo "started $(date -u +%H:%M) UTC; expect a FAILED alert within ~20 minutes"
  ;;
clean)
  sudo systemctl disable --now quantos-watchdog-selftest.timer 2>/dev/null || true
  sudo systemctl stop quantos-watchdog-selftest.service 2>/dev/null || true
  sudo rm -f $U.service $U.timer
  sudo systemctl daemon-reload
  sudo systemctl reset-failed quantos-watchdog-selftest.service 2>/dev/null || true
  echo "removed; the next watchdog run sends 'cleared FAILED quantos-watchdog-selftest'"
  ;;
*) echo "usage: $0 start|clean"; exit 2 ;;
esac
