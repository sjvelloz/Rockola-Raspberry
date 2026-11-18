#!/usr/bin/env bash
set -euo pipefail
PASS="${ROCKOLA_PI_PASS:-}"

# Escribir por base64 para no mezclar stdin de sudo -S
B64="$(printf '%s\n' 'saskweise ALL=(ALL) NOPASSWD: /sbin/reboot' | base64 -w0)"
printf '%s\n' "$PASS" | sudo -S bash -c "echo $B64 | base64 -d > /etc/sudoers.d/rockola-reboot && chmod 440 /etc/sudoers.d/rockola-reboot"

echo "=== file od ==="
printf '%s\n' "$PASS" | sudo -S od -c /etc/sudoers.d/rockola-reboot
echo "=== visudo ==="
printf '%s\n' "$PASS" | sudo -S visudo -cf /etc/sudoers.d/rockola-reboot
echo "=== cat ==="
printf '%s\n' "$PASS" | sudo -S cat /etc/sudoers.d/rockola-reboot
echo "=== END ==="
