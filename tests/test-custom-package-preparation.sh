#!/usr/bin/env bash
#
# Regression tests for sh/scripts-part2.sh custom package preparation.
#
# Derives the repo root from this script's location, so it can be copied to
# another checkout, and runs every production stage/function inside a freshly
# created temporary OpenWrt-like buildroot. It never mutates the caller's CWD,
# the real worktree, or any external evidence directory.
#
set -u

FAILED=0
fail() {
    echo "FAILED: $*" >&2
    FAILED=1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PART2="$PROJECT/sh/scripts-part2.sh"
[ -f "$PART2" ] || { echo "script missing: $PART2" >&2; exit 2; }
tmp_dirs=()
cleanup() {
    local d
    for d in "${tmp_dirs[@]}"; do
        [ -d "$d" ] && rm -rf -- "$d"
    done
}
trap cleanup EXIT

# Print a stable hash of every file (and existing file list) under the given
# directory, ignoring .git, so tests can assert nothing was changed there.
snapshot_hash() {
    local root="$1"
    find "$root" -path "$root/.git" -prune -o -type f -print 2>/dev/null | sort | xargs -r sha256sum 2>/dev/null | sha256sum | awk '{print $1}'
}

PROJECT_BEFORE="$(snapshot_hash "$PROJECT")"

# Start every test in a disposable buildroot. Production stages that touch
# ./feeds or ./package run only inside this sandbox. Sourcing the production
# script defines TARGET_DIR, REPOS, all helper functions, and the main guard.
# It must not run main automatically because ${BASH_SOURCE[0]} is not "$0".
fixture_buildroot() {
    local build
    build="$(mktemp -d -t custom-pkg-build.XXXXXX)"
    tmp_dirs+=("$build")
    mkdir -p "$build/feeds/packages/lang/rust" "$build/package" "$build/config"
    : > "$build/feeds/packages/lang/rust/Makefile"
    TARGET_DIR="$build/package/custom"
    mkdir -p "$TARGET_DIR"
    cd "$build" || exit 2
}

save_smartdns_happy() {
    mkdir -p "$TARGET_DIR/luci-app-smartdns" "$TARGET_DIR/openwrt-passwall-packages/smartdns"
    : > "$TARGET_DIR/luci-app-smartdns/Makefile"
    : > "$TARGET_DIR/openwrt-passwall-packages/smartdns/Makefile"
}

save_smartdns_duplicate() {
    save_smartdns_happy
    mkdir -p "$TARGET_DIR/smartdns/package/openwrt"
    : > "$TARGET_DIR/smartdns/package/openwrt/Makefile"
}

save_smartdns_missing_passwall() {
    mkdir -p "$TARGET_DIR/luci-app-smartdns"
    : > "$TARGET_DIR/luci-app-smartdns/Makefile"
}

save_nikki() {
    mkdir -p "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha" "$TARGET_DIR/OpenWrt-nikki/mihomo-meta"
    {
        echo 'PKG_NAME:=mihomo-alpha'
        echo 'PROVIDES:=mihomo'
        echo 'VARIANT:=alpha'
    } > "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile"
    {
        echo 'PKG_NAME:=mihomo-meta'
        echo 'PROVIDES:=mihomo'
        echo 'VARIANT:=meta'
        echo 'DEFAULT_VARIANT:=1'
        echo 'CONFLICTS:=mihomo-alpha'
    } > "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
}

save_nikki_fail_fixture() {
    # alpha has a valid reverse CONFLICTS, meta only has a commented
    # CONFLICTS. deconflict must fail without modifying either file.
    local dir="$1"
    mkdir -p "$dir/OpenWrt-nikki/mihomo-alpha" "$dir/OpenWrt-nikki/mihomo-meta"
    {
        echo 'PKG_NAME:=mihomo-alpha'
        echo 'PROVIDES:=mihomo'
        echo 'VARIANT:=alpha'
        echo 'CONFLICTS:=mihomo-meta'
    } > "$dir/OpenWrt-nikki/mihomo-alpha/Makefile"
    {
        echo 'PKG_NAME:=mihomo-meta'
        echo 'PROVIDES:=mihomo'
        echo 'VARIANT:=meta'
        echo 'DEFAULT_VARIANT:=1'
        echo '# CONFLICTS:=mihomo-alpha'
    } > "$dir/OpenWrt-nikki/mihomo-meta/Makefile"
}

sha256_file() {
    sha256sum "$1" | awk '{print $1}'
}

# Source the real production script once, after the first fixture buildroot is
# created. All later fixtures change TARGET_DIR with the function below.
fixture_buildroot
source "$PART2"
fixture() {
    local next
    next="$(mktemp -d -t custom-pkg-custom.XXXXXX)"
    tmp_dirs+=("$next")
    TARGET_DIR="$next/custom"
    mkdir -p "$TARGET_DIR" "$next/feeds/packages/lang/rust"
    : > "$next/feeds/packages/lang/rust/Makefile"
}

# 1) SmartDNS happy path (normal, then repeated/idempotent).
fixture
save_smartdns_happy
save_nikki
if ! verify_single_source_state; then
    fail "SmartDNS normal state should pass"
fi
if ! verify_single_source_state; then
    fail "SmartDNS repeat (idempotent) should pass"
fi

# 2) SmartDNS missing core must fail.
fixture
save_smartdns_missing_passwall
save_nikki
if verify_single_source_state; then
    fail "SmartDNS missing passwall definition should fail"
fi

# 3) SmartDNS duplicate independent pymumu definition must fail.
fixture
save_smartdns_duplicate
save_nikki
if verify_single_source_state; then
    fail "SmartDNS duplicate independent definition should fail"
fi

# 4) Nikki bidirectional conflicts is fixed to unidirectional meta->alpha,
# and repeated runs stay idempotent with exact necessary metadata.
fixture
save_nikki
sed '/PKG_NAME:=mihomo-alpha/a CONFLICTS:=mihomo-meta' "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile" > "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile.new"
mv "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile.new" "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile"
if ! deconflict_nikki_cores; then
    fail "Nikki bidirectional conflicts should be fixable"
fi
if ! deconflict_nikki_cores; then
    fail "Nikki idempotent repeat should pass"
fi
grep -q '^[[:space:]]*CONFLICTS:=mihomo-meta' "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile" && fail "Nikki alpha reverse conflicts should be removed"
grep -q '^[[:space:]]*CONFLICTS:=mihomo-alpha' "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile" || fail "Nikki meta conflicts protection must remain"
grep -q '^[[:space:]]*PROVIDES:=mihomo' "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile" || fail "Nikki alpha Provides must remain"
grep -q '^[[:space:]]*PROVIDES:=mihomo' "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile" || fail "Nikki meta Provides must remain"

# 5) Nikki missing makefiles must fail, not silently succeed.
fixture
mkdir -p "$TARGET_DIR/OpenWrt-nikki"
if deconflict_nikki_cores; then
    fail "Nikki missing mihomo makefiles should fail"
fi

# 6) Commented conflict rejection must leave both files byte-identical.
fixture
save_nikki_fail_fixture "$TARGET_DIR"
alpha_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")"
meta_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")"
if deconflict_nikki_cores; then
    fail "Nikki commented conflicts should be rejected"
fi
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")" = "$alpha_before" ] || fail "Nikki alpha must be unchanged on failure"
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")" = "$meta_before" ] || fail "Nikki meta must be unchanged on failure"

# 7) Nikki drift/unknown layout must fail without modifying files.
fixture
save_nikki
sed -i '/^CONFLICTS:=mihomo-alpha/d' "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
alpha_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")"
meta_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")"
if deconflict_nikki_cores; then
    fail "Nikki missing meta conflicts should fail"
fi
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")" = "$alpha_before" ] || fail "Nikki alpha must be unchanged on failure"
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")" = "$meta_before" ] || fail "Nikki meta must be unchanged on failure"

# 8) Nikki throws an active but malformed conflicts assignment must fail
# without modifying files.
fixture
save_nikki
sed -i '/^CONFLICTS:=mihomo-alpha/d' "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
echo 'CONFLICTS+=mihomo-alpha' >> "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
alpha_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")"
meta_before="$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")"
if deconflict_nikki_cores; then
    fail "Nikki malformed active conflicts assignment should fail"
fi
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile")" = "$alpha_before" ] || fail "Nikki alpha must be unchanged on failure"
[ "$(sha256_file "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile")" = "$meta_before" ] || fail "Nikki meta must be unchanged on failure"

# 9) PROVIDES matching must be token-exact: notmihomo must not satisfy it.
fixture
save_nikki
sed -i 's/^[[:space:]]*PROVIDES:=mihomo/PROVIDES:=notmihomo/' "$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
if deconflict_nikki_cores; then
    fail "Nikki PROVIDES notmihomo must not be accepted"
fi

# 10a/10b/11/12 run in fresh bash subprocesses so mocked functions do not
# leak into later fixtures.
bash_case() {
    local name="$1"
    local build="$2"
    local setup="$3"
    local call="$4"
    local expected_rc="${5:-1}"
    local out
    out="$(mktemp /tmp/${name}.XXXXXX)"
    LAST_CASE_OUT="$out"
    tmp_dirs+=("$out")
    if ! PART2="$PART2" BUILD="$build" bash -c '
        set -u
        source "$PART2"
        cd "$BUILD" || exit 2
        '"$setup"'
        set +e
        '"$call"'
        rc=$?
        echo "rc=$rc"
    ' > "$out" 2>&1; then
        fail "$name subprocess failed"
        cat "$out" >&2
        return 1
    fi
    grep -q "^rc=$expected_rc$" "$out" && return 0
    fail "$name should return rc=$expected_rc"
    cat "$out" >&2
    return 1
}

# 10a) main error propagation with a mocked clone that fails; later stages do
# not run, project files are unchanged.
build="$(mktemp -d -t custom-pkg-main.XXXXXX)"
tmp_dirs+=("$build")
mkdir -p "$build/feeds/packages/lang/rust" "$build/package/custom"
: > "$build/feeds/packages/lang/rust/Makefile"
project_after="$(snapshot_hash "$PROJECT")"
bash_case main-clone-failure "$build" '
clone_custom_repos() { echo mock-clone-fail >&2; return 1; }
verify_turboacc_makefile() { echo LATER >&2; return 0; }
verify_single_source_state() { echo LATER >&2; return 0; }
' 'main'
if grep -q 'LATER' "$LAST_CASE_OUT"; then
    fail "stages after clone failure must not run"
fi
[ "$(snapshot_hash "$PROJECT")" = "$project_after" ] || fail "main failure must not mutate project"

# 10b) verify_single_source_state failure propagates from main as non-zero;
# earlier stages are mocked to succeed, then the real final stage fails.
build="$(mktemp -d -t custom-pkg-main.XXXXXX)"
tmp_dirs+=("$build")
mkdir -p "$build/package/custom/openwrt-passwall-packages/smartdns" \
         "$build/package/custom/luci-app-smartdns" \
         "$build/package/custom/smartdns/package/openwrt"
: > "$build/package/custom/openwrt-passwall-packages/smartdns/Makefile"
: > "$build/package/custom/luci-app-smartdns/Makefile"
: > "$build/package/custom/smartdns/package/openwrt/Makefile"
bash_case main-single-source-failure "$build" '
patch_rust_makefile() { return 0; }
reset_custom_package_dir() { return 0; }
remove_conflicting_makefiles() { return 0; }
clone_custom_repos() { return 0; }
flatten_feed_layout_repos() { return 0; }
verify_turboacc_makefile() { return 0; }
' 'main'
[ "$(snapshot_hash "$PROJECT")" = "$project_after" ] || fail "main failure must not mutate project"

# 11) Dangerous reset works only for a valid TARGET_DIR; a bad path must be
# rejected without touching the real worktree.
build5="$(mktemp -d -t custom-pkg-reset.XXXXXX)"; tmp_dirs+=("$build5")
bash_case reset-empty-reject "$build5" 'TARGET_DIR=""' 'reset_custom_package_dir'
build6="$(mktemp -d -t custom-pkg-reset.XXXXXX)"; tmp_dirs+=("$build6")
bash_case reset-root-reject "$build6" 'TARGET_DIR="/"' 'reset_custom_package_dir'

# 12) reset/find/mkdir failures inside production stages must propagate.
# Run each in a fresh bash process so mocked shell builtins/functions do not
# leak into later fixtures.
build2="$(mktemp -d -t custom-pkg-probe.XXXXXX)"; tmp_dirs+=("$build2")
bash_case reset-rm-failure "$build2" 'TARGET_DIR="$(mktemp -d)"; rm() { return 1; }' 'reset_custom_package_dir'
build3="$(mktemp -d -t custom-pkg-probe.XXXXXX)"; tmp_dirs+=("$build3")
bash_case reset-mkdir-failure "$build3" 'TARGET_DIR="$(mktemp -d)"; mkdir() { return 1; }' 'reset_custom_package_dir'
build4="$(mktemp -d -t custom-pkg-probe.XXXXXX)"; tmp_dirs+=("$build4")
bash_case remove-find-failure "$build4" 'find() { return 3; }' 'remove_conflicting_makefiles'

if [ "$FAILED" != "0" ]; then
    echo "test-custom-package-preparation: FAILURE" >&2
    exit 1
fi
echo "test-custom-package-preparation: OK"
exit 0
