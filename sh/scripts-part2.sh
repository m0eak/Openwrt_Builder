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
    ["https://github.com/pymumu/smartdns"]=""
    ["https://github.com/sbwml/v2ray-geodata"]=""
    ["https://github.com/vernesong/OpenClash.git"]=""
    ["https://github.com/eamonxg/luci-theme-aurora"]=""
    ["https://github.com/eamonxg/luci-theme-shadcn.git"]=""
    ["https://github.com/eamonxg/luci-app-aurora-config"]=""
    ["https://github.com/NONGFAH/luci-app-athena-led.git"]=""
    ["https://github.com/Tokisaki-Galaxy/luci-app-tailscale-community.git"]=""
    ["https://github.com/m0eak/openwrt-gecoosac.git"]=""
    ["https://github.com/miaoermua/luci-app-leigod-acc.git"]=""
    ["https://github.com/nikkinikki-org/OpenWrt-momo"]=""
    ["https://github.com/EasyTier/luci-app-easytier"]="v2.6.4"
    ["https://github.com/Openwrt-Passwall/openwrt-passwall2"]=""
    ["https://github.com/Openwrt-Passwall/openwrt-passwall"]=""
    ["https://github.com/Openwrt-Passwall/openwrt-passwall-packages"]=""
    # ["https://github.com/immortalwrt/homeproxy"]=""
    ["https://github.com/10000ge10000/luci-app-openclaw"]=""
    ["https://github.com/Slava-Shchipunov/awg-openwrt"]=""
    ["https://github.com/QiuSimons/luci-app-daed"]=""
)

CONFLICTING_MAKEFILE_KEYWORDS=(
    "mosdns"
    "openclash"
    "luci-app-lucky"
    "smartdns"
    "v2ray-geodata"
    "daed"
)

patch_rust_makefile() {
    if [ -e "feeds/packages/lang/rust/Makefile" ]; then
        sed -i 's/--set=llvm\.download-ci-llvm=true/--set=llvm.download-ci-llvm=false/' feeds/packages/lang/rust/Makefile
    fi
}

reset_custom_package_dir() {
    if [ -z "$TARGET_DIR" ] || [ "$TARGET_DIR" = "/" ]; then
        echo "错误: TARGET_DIR 异常，拒绝删除: '$TARGET_DIR'"
        exit 1
    fi

    rm -rf "$TARGET_DIR"
    mkdir -p "$TARGET_DIR"
}

remove_conflicting_makefiles() {
    local keyword
    local file
    local file_lower

    echo "开始清理 feeds 中会被 package/custom 覆盖的 Makefile"
    find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
    while IFS= read -r -d $'\0' file; do
        file_lower="${file,,}"
        for keyword in "${CONFLICTING_MAKEFILE_KEYWORDS[@]}"; do
            if [[ "$file_lower" == *"$keyword"* ]]; then
                echo "删除冲突 Makefile: $file"
                rm -f "$file"
                break
            fi
        done
    done
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
        exit 1
    fi
    echo "所有自定义仓库克隆完成"
}

verify_turboacc_makefile() {
    local turboacc_luci_dir

    turboacc_luci_dir="$(find "$TARGET_DIR/turboacc" -maxdepth 1 -type d -name 'luci-app*' | head -n 1)"
    if [ -z "$turboacc_luci_dir" ] || [ ! -f "$turboacc_luci_dir/Makefile" ]; then
        echo "未找到 turboacc 的 luci-app Makefile，终止 GitHub Action"
        exit 1
    fi

    echo "找到 turboacc Makefile，继续执行"
}

patch_rust_makefile
reset_custom_package_dir
remove_conflicting_makefiles
clone_custom_repos
verify_turboacc_makefile
