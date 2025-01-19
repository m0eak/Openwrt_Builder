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

# Modify default IP
# 排除 $PWD/package 目录及其子目录下的 Makefile
find . -type f -name "Makefile" ! -path "$PWD/package*" | grep mosdns | xargs rm -f

TARGET_DIR="$PWD/package"
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "$home 目录下未找到 源码仓库，请确保源码仓库在目录下，请善用 mv 命令移动源码仓库$"
    exit 1
fi

REPOS=(
    "https://github.com/sbwml/luci-app-mosdns"
    "https://github.com/chenmozhijin/turboacc"
    "https://github.com/breeze303/luci-app-lucky"
    "https://github.com/JiaY-Shi/fancontrol"
    "https://github.com/animegasan/luci-app-wolplus"
)

update_or_clone_repo() {
    repo_url=$1
    repo_name=$(basename -s .git "$repo_url")
    repo_dir="$TARGET_DIR/$repo_name"

    # 排除 $PWD/package 目录及其子目录下的 Makefile
    find . -type f -name "Makefile" ! -path "$PWD/package*" | grep "$repo_name" | xargs rm -f

    if [ ! -d "$repo_dir" ]; then
        echo -e "${GREEN}Cloning $repo_name${NC}"
        git clone --single-branch --depth 1 "$repo_url" "$repo_dir"
    else
        echo -e "${GREEN}Updating $repo_name${NC}"
        cd "$repo_dir" || exit
        git pull
        cd - || exit
    fi

}

for repo in "${REPOS[@]}"; do
    update_or_clone_repo "$repo"
done

echo -e "${GREEN}All repositories are up to date.${NC}"
