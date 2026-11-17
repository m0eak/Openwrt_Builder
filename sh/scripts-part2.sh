#!/bin/bash
#
# Copyright (c) 2019-2020 P3TERX <https://p3terx.com>
#
# This is free software, licensed under the MIT License.
# See /LICENSE for more information.
#
# https://github.com/P3TERX/Actions-OpenWrt
# File name: diy-part2.sh
# Description: OpenWrt DIY script part 2 (After Update feeds)
#

TARGET_DIR="${PWD}/package/custom"

declare -A REPOS=(
    ["https://github.com/sbwml/luci-app-mosdns"]=""
    ["https://github.com/chenmozhijin/turboacc"]=""
    ["https://github.com/gdy666/luci-app-lucky"]=""
    ["https://github.com/m0eak/fancontrol"]=""
    ["https://github.com/animegasan/luci-app-wolplus"]=""
    ["https://github.com/0x676e67/luci-theme-design"]="js"
    ["https://github.com/0x676e67/luci-app-design-config.git"]=""
    ["https://github.com/nikkinikki-org/OpenWrt-nikki"]=""
    ["https://github.com/sirpdboy/luci-app-partexp"]=""
    ["https://github.com/pymumu/luci-app-smartdns"]=""
    ["https://github.com/sbwml/v2ray-geodata"]=""
    ["https://github.com/vernesong/OpenClash.git"]=""
    ["https://github.com/eamonxg/luci-theme-aurora"]=""
    ["https://github.com/eamonxg/luci-theme-shadcn.git"]=""
    ["https://github.com/anothaDev/luci-theme-vantage"]=""
    ["https://github.com/eamonxg/luci-app-aurora-config"]=""
    ["https://github.com/NONGFAH/luci-app-athena-led.git"]=""
    ["https://github.com/Tokisaki-Galaxy/luci-app-tailscale-community.git"]=""
    ["https://github.com/m0eak/openwrt-gecoosac.git"]=""
    ["https://github.com/miaoermua/luci-app-leigod-acc.git"]=""
    ["https://github.com/EasyTier/luci-app-easytier"]="v2.6.4"
    ["https://github.com/Openwrt-Passwall/openwrt-passwall2"]=""
    ["https://github.com/Openwrt-Passwall/openwrt-passwall"]=""
    ["https://github.com/Openwrt-Passwall/openwrt-passwall-packages"]=""
    # ["https://github.com/fw876/helloworld"]="v196.3"  # 移除：与 sbwml 的 luci-app-mosdns 内核冲突；代理依赖由 passwall-packages + sbwml 满足
    # ["https://github.com/immortalwrt/homeproxy"]=""
    ["https://github.com/10000ge10000/luci-app-openclaw"]=""
    ["https://github.com/Slava-Shchipunov/awg-openwrt"]=""
    ["https://github.com/QiuSimons/luci-app-daed"]=""
    ["https://github.com/sirpdboy/luci-app-ddns-go.git"]=""
    ["https://github.com/tty228/luci-app-wechatpush.git"]=""
    ["https://github.com/gaoderby/luci-app-kms.git"]=""
    ["https://github.com/sbwml/luci-app-ramfree.git"]=""
    ["https://github.com/lisaac/luci-app-diskman"]=""
)

CONFLICTING_MAKEFILE_KEYWORDS=(
    "mosdns"
    "openclash"
    "luci-app-lucky"
    "smartdns"
    "v2ray-geodata"
    "xray-core"
    "daed"
    "ddns-go"
)

patch_rust_makefile() {
    if [ -e "feeds/packages/lang/rust/Makefile" ]; then
        sed -i 's/--set=llvm\.download-ci-llvm=true/--set=llvm.download-ci-llvm=false/' feeds/packages/lang/rust/Makefile || return 1
    fi
}

reset_custom_package_dir() {
    if [ -z "$TARGET_DIR" ] || [ "$TARGET_DIR" = "/" ]; then
        echo "错误: TARGET_DIR 异常，拒绝删除: '$TARGET_DIR'"
        return 1
    fi

    rm -rf "$TARGET_DIR" || { echo "错误: 删除 package/custom 失败: $TARGET_DIR" >&2; return 1; }
    mkdir -p "$TARGET_DIR" || { echo "错误: 创建 package/custom 失败: $TARGET_DIR" >&2; return 1; }
}

remove_conflicting_makefiles() {
    local keyword
    local file
    local file_lower
    local failed=0
    local find_list

    echo "开始清理 feeds 中会被 package/custom 覆盖的 Makefile"
    find_list="$(mktemp /tmp/custom-pkg-find.XXXXXX)" || { echo "错误: 无法创建临时文件" >&2; return 1; }
    if ! find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 > "$find_list"; then
        echo "错误: 扫描冲突 Makefile 失败" >&2
        rm -f "$find_list"
        return 1
    fi
    while IFS= read -r -d $'\0' file; do
        file_lower="${file,,}"
        for keyword in "${CONFLICTING_MAKEFILE_KEYWORDS[@]}"; do
            if [[ "$file_lower" == *"$keyword"* ]]; then
                echo "删除冲突 Makefile: $file"
                rm -f "$file" || { echo "错误: 删除冲突 Makefile 失败: $file" >&2; failed=1; }
                break
            fi
        done
    done < "$find_list"
    rm -f "$find_list"
    if [ "$failed" -ne 0 ]; then
        echo "错误: 冲突 Makefile 清理未完整完成" >&2
        return 1
    fi
    echo "冲突 Makefile 清理完成"
}

clone_repo() {
    local repo_url="$1"
    local repo_branch="${REPOS[$repo_url]}"
    local repo_name
    local repo_dir

    repo_name="$(basename -s .git "$repo_url")"
    repo_dir="$TARGET_DIR/$repo_name"

    if [ -d "$repo_dir" ]; then
        echo "目录 $repo_dir 已存在，跳过克隆"
        return 0
    fi

    echo "克隆仓库: $repo_name, URL: $repo_url, 分支: ${repo_branch:-默认分支}"
    if [ -z "$repo_branch" ]; then
        git clone --single-branch --depth 1 "$repo_url" "$repo_dir"
    else
        git clone --single-branch --depth 1 -b "$repo_branch" "$repo_url" "$repo_dir"
    fi
}

clone_custom_repos() {
    local repo
    local failed=0

    echo "开始克隆自定义仓库"
    for repo in "${!REPOS[@]}"; do
        if clone_repo "$repo"; then
            echo "仓库克隆完成: $(basename -s .git "$repo")"
        else
            echo "仓库克隆失败: $repo"
            failed=$((failed + 1))
        fi
    done

    if [ "$failed" -ne 0 ]; then
        echo "错误: $failed 个自定义仓库克隆失败"
        return 1
    fi
    echo "所有自定义仓库克隆完成"
}

verify_turboacc_makefile() {
    local turboacc_luci_dir

    turboacc_luci_dir="$(find "$TARGET_DIR/turboacc" -maxdepth 1 -type d -name 'luci-app*' | head -n 1)"
    if [ -z "$turboacc_luci_dir" ] || [ ! -f "$turboacc_luci_dir/Makefile" ]; then
        echo "未找到 turboacc 的 luci-app Makefile，终止 GitHub Action"
        return 1
    fi

    echo "找到 turboacc Makefile，继续执行"
}

flatten_feed_layout_repos() {
    # gaoderby/luci-app-kms 是 feed 布局 (package/network/vlmcsd + luci/applications/luci-app-vlmcsd)
    # 直接放在 package/custom/ 下不会被扫描，需展开为独立包目录
    local feed_dir="$TARGET_DIR/luci-app-kms"

    if [ ! -d "$feed_dir" ]; then
        return 0
    fi

    echo "展开 feed 布局仓库: luci-app-kms"
    if [ ! -d "$feed_dir/package/network/vlmcsd" ] || [ ! -d "$feed_dir/luci/applications/luci-app-vlmcsd" ]; then
        echo "错误: luci-app-kms feed 布局缺少预期包目录" >&2
        return 1
    fi
    mv "$feed_dir/package/network/vlmcsd" "$TARGET_DIR/vlmcsd" || return 1
    mv "$feed_dir/luci/applications/luci-app-vlmcsd" "$TARGET_DIR/luci-app-vlmcsd" || return 1
    rm -rf "$feed_dir" || { echo "错误: 删除已展开的 luci-app-kms 目录失败" >&2; return 1; }
    echo "已展开: package/custom/vlmcsd + package/custom/luci-app-vlmcsd"
}

flatten_vantage_repo() {
    # 将 Vantage 双包仓库展开为两个可被 OpenWrt 发现的包目录。
    local src="$TARGET_DIR/luci-theme-vantage"
    local theme_tmp="$TARGET_DIR/.luci-theme-vantage.pkg"

    if [ ! -d "$src/luci-theme-vantage" ]; then
        return 0
    fi

    echo "展开双包仓库: luci-theme-vantage"
    rm -rf "$theme_tmp" || return 1
    mv "$src/luci-theme-vantage" "$theme_tmp" || return 1
    if [ -d "$src/luci-app-vantage" ]; then
        mv "$src/luci-app-vantage" "$TARGET_DIR/luci-app-vantage" || return 1
    fi
    rm -rf "$src" || return 1
    mv "$theme_tmp" "$TARGET_DIR/luci-theme-vantage" || return 1
    echo "已展开: package/custom/luci-theme-vantage + package/custom/luci-app-vantage"
}

resolve_smartdns_duplicates() {
    # 只保留 passwall-packages 的 OpenWrt 集成布局：独立 pymumu/smartdns
    # 仓库的 package/openwrt/Makefile 含相对 rust include，且会造成重复定义。
    # 本函数用于新克隆完成后仍发现重复定义时发出错误，避免静默生成递归 Kconfig。
    local smartdns_dir="$TARGET_DIR/smartdns"
    local passwall_smartdns="$TARGET_DIR/openwrt-passwall-packages/smartdns/Makefile"
    local luci_app="$TARGET_DIR/luci-app-smartdns/Makefile"

    if [ -f "$smartdns_dir/package/openwrt/Makefile" ]; then
        echo "错误: 仍发现独立 smartdns 定义 $smartdns_dir/package/openwrt/Makefile，保留 passwall-packages 集成来源"
        return 1
    fi
    if [ ! -f "$passwall_smartdns" ]; then
        echo "错误: 缺少 passwall-packages smartdns Makefile: $passwall_smartdns"
        return 1
    fi
    if [ ! -f "$luci_app" ]; then
        echo "错误: 缺少 luci-app-smartdns Makefile: $luci_app"
        return 1
    fi
    echo "smartdns 来源唯一: openwrt-passwall-packages/smartdns + luci-app-smartdns"
}

_nikki_active_conflicts_lines() {
    # 只收集激活（非注释）的 CONFLICTS 赋值，输出 "op:value" 逐行。
    # 形如 "# CONFLICTS:=mihomo-alpha" 的注释不会被当作有效声明。
    local makefile="$1"
    awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*CONFLICTS[[:space:]]*[+?]?:?=/ {
            line = $0
            sub(/^[[:space:]]*CONFLICTS[[:space:]]*/, "", line)
            if (line ~ /^:=/) { op = ":="; sub(/^:=/, "", line) }
            else if (line ~ /^\+=/) { op = "+="; sub(/^\+=/, "", line) }
            else if (line ~ /^\?=/) { op = "?="; sub(/^\?=/, "", line) }
            else if (line ~ /^=/) { op = "="; sub(/^=/, "", line) }
            else { next }
            sub(/^[[:space:]]*/, "", line)
            sub(/[[:space:]]*#.*$/, "", line)
            sub(/[[:space:]]+$/, "", line)
            print op ":" line
        }
    ' "$makefile"
}

_nikki_has_provides_mihomo() {
    local makefile="$1"
    local line
    local token

    line="$(grep -E '^[[:space:]]*PROVIDES[[:space:]]*:=' "$makefile" | head -n 1 || true)"
    [ -n "$line" ] || return 1
    line="${line#*=}"
    line="${line%%#*}"
    for token in $line; do
        if [ "$token" = "mihomo" ]; then
            return 0
        fi
    done
    return 1
}

deconflict_nikki_cores() {
    # OpenWrt Kconfig 由 CONFLICTS 生成 "depends on m || (PACKAGE_x != y)"。
    # alpha/meta 双向声明会变成互相依赖并触发 Kconfig 递归。
    # 这里只处理默认构建系统生成的配置内建互斥：保留稳定 default
    # variant(mihomo-meta) 对 alpha 的冲突声明，移除 alpha 对 meta 的反向
    # 声明，避免 Kconfig 循环。安装包管理器（APK）层的运行时冲突未验证。
    local alpha_makefile="$TARGET_DIR/OpenWrt-nikki/mihomo-alpha/Makefile"
    local meta_makefile="$TARGET_DIR/OpenWrt-nikki/mihomo-meta/Makefile"
    local alpha_conflicts meta_conflicts conflict_line conflict_count

    if [ ! -f "$alpha_makefile" ] || [ ! -f "$meta_makefile" ]; then
        echo "错误: Nikki mihomo Makefile 缺失: alpha=$alpha_makefile meta=$meta_makefile" >&2
        return 1
    fi

    # 先验证锚定，再修改，避免失败留下半成品。
    if ! grep -Eq '^[[:space:]]*PKG_NAME:=mihomo-alpha[[:space:]]*$' "$alpha_makefile" || \
       ! grep -Eq '^[[:space:]]*VARIANT[[:space:]]*:=alpha[[:space:]]*$' "$alpha_makefile"; then
        echo "错误: mihomo-alpha Makefile 锚定无效: $alpha_makefile" >&2
        return 1
    fi
    if ! grep -Eq '^[[:space:]]*PKG_NAME:=mihomo-meta[[:space:]]*$' "$meta_makefile" || \
       ! grep -Eq '^[[:space:]]*VARIANT[[:space:]]*:=meta[[:space:]]*$' "$meta_makefile" || \
       ! grep -Eq '^[[:space:]]*DEFAULT_VARIANT[[:space:]]*:=1[[:space:]]*$' "$meta_makefile"; then
        echo "错误: mihomo-meta Makefile 锚定无效: $meta_makefile" >&2
        return 1
    fi
    if ! _nikki_has_provides_mihomo "$alpha_makefile" || ! _nikki_has_provides_mihomo "$meta_makefile"; then
        echo "错误: mihomo PROVIDES 声明缺失: $alpha_makefile / $meta_makefile" >&2
        return 1
    fi

    # 任何修改之前先校验 alpha 布局与 meta 的有效保护，失败时两个文件都保持原样。
    alpha_conflicts="$(_nikki_active_conflicts_lines "$alpha_makefile")"
    if [ -n "$alpha_conflicts" ]; then
        conflict_count="$(printf '%s\n' "$alpha_conflicts" | grep -c . || true)"
        if [ "$conflict_count" -ne 1 ] || [ "$alpha_conflicts" != ":=:mihomo-meta" ]; then
            echo "错误: mihomo-alpha CONFLICTS 布局未知/漂移: '$alpha_conflicts'" >&2
            return 1
        fi
    fi
    meta_conflicts="$(_nikki_active_conflicts_lines "$meta_makefile")"
    conflict_count="$(printf '%s\n' "$meta_conflicts" | grep -c . || true)"
    if [ "$conflict_count" -ne 1 ] || [ "$meta_conflicts" != ":=:mihomo-alpha" ]; then
        echo "错误: mihomo-meta 缺少准确激活的 CONFLICTS:=mihomo-alpha 保护 (found: '$meta_conflicts')" >&2
        return 1
    fi

    if [ -n "$alpha_conflicts" ]; then
        sed -i '/^[[:space:]]*CONFLICTS[[:space:]]*:=[[:space:]]*mihomo-meta[[:space:]]*$/d' "$alpha_makefile" || {
            echo "错误: 移除 mihomo-alpha 反向 CONFLICTS 失败" >&2
            return 1
        }
        alpha_conflicts="$(_nikki_active_conflicts_lines "$alpha_makefile")"
        if [ -n "$alpha_conflicts" ]; then
            echo "错误: mihomo-alpha 在修改后仍残留激活 CONFLICTS: '$alpha_conflicts'" >&2
            return 1
        fi
    fi
    echo "Nikki 核心冲突已收敛: mihomo-meta 保留 CONFLICTS=mihomo-alpha，mihomo-alpha 不再反向声明"
}

verify_single_source_state() {
    resolve_smartdns_duplicates || return 1
    deconflict_nikki_cores || return 1
}

main() {
    patch_rust_makefile || { echo "错误: patch_rust_makefile 失败" >&2; return 1; }
    reset_custom_package_dir || { echo "错误: 重置 package/custom 失败" >&2; return 1; }
    remove_conflicting_makefiles || { echo "错误: 冲突 Makefile 清理失败" >&2; return 1; }
    clone_custom_repos || { echo "错误: 自定义仓库克隆失败" >&2; return 1; }
    flatten_feed_layout_repos || { echo "错误: feed 布局展开失败" >&2; return 1; }
    flatten_vantage_repo || { echo "错误: Vantage 布局展开失败" >&2; return 1; }
    verify_turboacc_makefile || { echo "错误: turboacc Makefile 校验失败" >&2; return 1; }
    verify_single_source_state || { echo "错误: 单一来源状态校验失败" >&2; return 1; }
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
    exit $?
fi
