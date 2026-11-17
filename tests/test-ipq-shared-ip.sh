#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PART1="$PROJECT/sh/scripts-part1.sh"
fixture="$(mktemp -d -t ipq-shared-ip.XXXXXX)"
trap 'rm -rf "$fixture"' EXIT

# Load only the production patch helper, without running feed downloads.
sed -n '/^set_board_aware_lan_ip()/,/^# --- 根据 WORKFLOW_NAME/p' "$PART1" > "$fixture/helper.sh"
source "$fixture/helper.sh"
cd "$fixture"
config=package/base-files/files/bin/config_generate
mkdir -p "$(dirname "$config")"

write_original_fixture() {
    cat > "$config" <<'EOF'
#!/bin/sh
# All board/network fixtures remain inside this test's temporary directory.
cat() {
    if [ "$1" = /tmp/sysinfo/board_name ]; then
        command cat "$BOARD_FILE"
    else
        command cat "$@"
    fi
}
if [ -s "$NETWORK_FILE" ]; then
    cat "$NETWORK_FILE"
    exit 0
fi
generate_network() {
    local ipad
    case "$1" in
        lan) ipad=${ipaddr:-"192.168.1.1"} ;;
        *) ipad=${ipaddr:-"192.168.9.1"} ;;
    esac
    printf '%s\n' "$ipad"
}
generate_network lan
EOF
    chmod 755 "$config"
}

run_config() {
    BOARD_FILE="$fixture/board" NETWORK_FILE="$fixture/network" \
        ipaddr="${1:-}" "./$config"
}

write_original_fixture
set_board_aware_lan_ip
test "$(stat -c %a "$config")" = 755
/bin/sh -n "$config"
first="$(sha256sum "$config")"
set_board_aware_lan_ip
test "$first" = "$(sha256sum "$config")"

for pair in glinet,gl-axt1800:192.168.8.1 jdcloud,re-cs-02:192.168.100.1 unknown,board:192.168.1.1; do
    printf '%s\n' "${pair%:*}" > "$fixture/board"
    test "$(run_config)" = "${pair#*:}"
done
test "$(run_config 192.168.66.6)" = 192.168.66.6
printf '%s\n' 'preserved user network settings' > "$fixture/network"
network_before="$(sha256sum "$fixture/network")"
test "$(run_config)" = 'preserved user network settings'
test "$network_before" = "$(sha256sum "$fixture/network")"

# Missing LAN/function anchors and corrupt existing patches fail atomically.
for drift in lan function existing; do
    write_original_fixture
    case "$drift" in
        lan) sed -i 's/192.168.1.1/192.168.99.1/' "$config" ;;
        function) sed -i 's/generate_network() {/generate_network() { # changed/' "$config" ;;
        existing)
            set_board_aware_lan_ip >/dev/null
            sed -i 's/192.168.8.1/192.168.88.1/' "$config"
            ;;
    esac
    before="$(sha256sum "$config")"
    if set_board_aware_lan_ip; then
        echo "Expected failure for $drift drift" >&2
        exit 1
    fi
    test "$before" = "$(sha256sum "$config")"
    test "$(stat -c %a "$config")" = 755
done

echo "test-ipq-shared-ip: OK"
