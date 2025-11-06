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

# 定义目标目录
[ -e feeds/packages/lang/rust/Makefile ] && sed -i 's/--set=llvm\.download-ci-llvm=true/--set=llvm.download-ci-llvm=false/' feeds/packages/lang/rust/Makefile
TARGET_DIR="$PWD/package"

# 定义要克隆的仓库和分支
declare -A REPOS=(
    ["https://github.com/sbwml/luci-app-mosdns"]=""  # 使用默认分支
    ["https://github.com/breeze303/luci-app-lucky.git"]="" # 使用默认分支
    ["https://github.com/chenmozhijin/turboacc"]="" # 使用默认分支
    ["https://github.com/breeze303/luci-app-lucky"]="" # 使用默认分支
    ["https://github.com/m0eak/fancontrol"]="" # 使用默认分支
    ["https://github.com/animegasan/luci-app-wolplus"]="" # 使用默认分支
    ["https://github.com/m0eak/luci-theme-asus"]="js"  # 指定 js 分支
    ["https://github.com/0x676e67/luci-theme-design"]="js"  # 指定 js 分支
    ["https://github.com/0x676e67/luci-app-design-config.git"]="" # 使用默认分支
    ["https://github.com/nikkinikki-org/OpenWrt-nikki"]="" # 使用默认分支
    ["https://github.com/sirpdboy/luci-app-partexp"]="" # 使用默认分支
    ["https://github.com/pymumu/luci-app-smartdns"]="" # 使用默认分支
    ["https://github.com/pymumu/smartdns"]="" # 使用默认分支
    ["https://github.com/sbwml/v2ray-geodata"]=""
    ["https://github.com/vernesong/OpenClash.git"]=""
    ["https://github.com/eamonxg/luci-theme-aurora"]=""
    ["https://github.com/NONGFAH/luci-app-athena-led.git"]=""
    ["https://github.com/sirpdboy/luci-app-netspeedtest.git"]="js"
    
)

# 删除 mosdns 相关的 Makefile
echo "开始查找并删除 mosdns 相关的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
while IFS= read -r -d $'\0' file; do
    if [[ "$file" == *"mosdns"* ]]; then
        echo "删除 Makefile: $file"
        rm -f "$file"
    fi
done
echo "mosdns 相关的 Makefile 清理完成"

echo "开始查找并删除 OpenClash 相关的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
while IFS= read -r -d $'\0' file; do
    if [[ "$file" == *"openclash"* ]]; then
        echo "删除 Makefile: $file"
        rm -f "$file"
    fi
done
echo "mosdns 相关的 Makefile 清理完成"

echo "开始查找并删除 luci-app-lucky 相关的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
while IFS= read -r -d $'\0' file; do
    if [[ "$file" == *"luci-app-lucky"* ]]; then
        echo "删除 Makefile: $file"
        rm -f "$file"
    fi
done
echo "luci-app-lucky 相关的 Makefile 清理完成"

echo "开始查找并删除 smartdns 相关的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
while IFS= read -r -d $'\0' file; do
    if [[ "$file" == *"smartdns"* ]]; then
        echo "删除 Makefile: $file"
        rm -f "$file"
    fi
done
echo "smartdns 相关的 Makefile 清理完成"

echo "开始查找并删除 v2ray 相关的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" -print0 |
while IFS= read -r -d $'\0' file; do
    if [[ "$file" == *"v2ray-geodata"* ]]; then
        echo "删除 Makefile: $file"
        rm -f "$file"
    fi
done
echo "v2ray-geodata 相关的 Makefile 清理完成"
# 克隆仓库
clone_repo() {
    local repo_url=$1
    local repo_branch=${REPOS[$repo_url]}
    local repo_name=$(basename -s .git "$repo_url")
    local repo_dir="$TARGET_DIR/$repo_name"

    echo "克隆仓库: $repo_name, URL: $repo_url, 分支: $repo_branch"

    if [ -d "$repo_dir" ]; then
        echo "目录 $repo_dir 已存在，跳过克隆"
        return
    fi

    if [ -z "$repo_branch" ]; then
        echo "执行 git clone (默认分支): git clone --single-branch --depth 1 \"$repo_url\" \"$repo_dir\""
        git clone --single-branch --depth 1 "$repo_url" "$repo_dir"
    else
        echo "执行 git clone (指定分支): git clone --single-branch --depth 1 -b \"$repo_branch\" \"$repo_url\" \"$repo_dir\""
        git clone --single-branch --depth 1 -b "$repo_branch" "$repo_url" "$repo_dir"
    fi

    if [ $? -eq 0 ]; then
        echo "仓库 $repo_name 克隆完成"
    else
        echo "仓库 $repo_name 克隆失败"
    fi
}

# 遍历 REPOS 数组并克隆仓库
echo "开始遍历 REPOS 数组并克隆仓库"
for repo in "${!REPOS[@]}"; do
    clone_repo "$repo"
done

echo "所有仓库克隆完成"
cd $TARGET_DIR/turboacc/luci-app*
if [ "$(ls -la | grep -c "Makefile")" -eq '0' ]; then
    echo "未找到 Makefile，终止 GitHub Action"
    exit 1
else
    echo "找到 Makefile，继续执行"
fi
