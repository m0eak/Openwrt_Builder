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
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

TARGET_DIR="$PWD/package"
echo "检查 TARGET_DIR: $TARGET_DIR"
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED} $PWD/package 目录下未找到 源码仓库，请确保源码仓库在目录下，请善用 mv 命令移动源码仓库 ${NC}"
    exit 1
fi

# 修改 REPOS 数组，使其支持分支信息
declare -A REPOS
REPOS=(
    ["https://github.com/sbwml/luci-app-mosdns"]=""  # 使用默认分支
    ["https://github.com/chenmozhijin/turboacc"]="" # 使用默认分支
    ["https://github.com/breeze303/luci-app-lucky"]="" # 使用默认分支
    ["https://github.com/JiaY-Shi/fancontrol"]="" # 使用默认分支
    ["https://github.com/animegasan/luci-app-wolplus"]="" # 使用默认分支
    ["https://github.com/m0eak/luci-theme-asus"]="js"  # 指定 js 分支
    ["https://github.com/0x676e67/luci-theme-design"]="js"  # 指定 js 分支
)

# 提取仓库名称列表，去掉 "luci-app-" 前缀
declare -a repo_names
for repo_url in "${!REPOS[@]}"; do
    repo_name=$(basename -s .git "$repo_url")
    repo_name=${repo_name#luci-app-} # 去掉 "luci-app-" 前缀
    repo_names+=("$repo_name")
done

# 删除所有符合条件的 Makefile
echo "开始查找并删除符合条件的 Makefile"
find . -type f -name "Makefile" ! -path "$TARGET_DIR/*" |
while IFS= read -r file; do
  for repo_name in "${repo_names[@]}"; do
    if [[ "$file" == *"$repo_name"* ]]; then
      echo "现有的reponame:$repo_name"
      echo "删除 Makefile: $file"
      rm -f "$file"
      break # 找到匹配的仓库名称，跳出内层循环
    fi
  done
done
echo "Makefile 清理完成"

update_or_clone_repo() {
    local repo_url=$1
    local repo_branch=${REPOS[$repo_url]}
    local repo_name=$(basename -s .git "$repo_url")
    local repo_dir="$TARGET_DIR/$repo_name"

    echo "处理仓库: $repo_name, URL: $repo_url, 分支: $repo_branch"

    if [ ! -d "$repo_dir" ]; then
        echo -e "${GREEN}Cloning $repo_name${NC}"
        if [ -z "$repo_branch" ]; then
            echo "执行 git clone (默认分支): git clone --single-branch --depth 1 \"$repo_url\" \"$repo_dir\""
            git clone --single-branch --depth 1 "$repo_url" "$repo_dir"
            echo "仓库 $repo_name 克隆完成"
        else
            echo "执行 git clone (指定分支): git clone --single-branch --depth 1 -b \"$repo_branch\" \"$repo_url\" \"$repo_dir\""
            git clone --single-branch --depth 1 -b "$repo_branch" "$repo_url" "$repo_dir"
            echo "仓库 $repo_name 克隆完成"
        fi
    else
        echo -e "${GREEN}Updating $repo_name${NC}"
        cd "$repo_dir" || exit
        echo "执行 git pull"
        git pull
        if [ $? -eq 0 ]; then
          echo "仓库 $repo_name 更新完成"
        else
          echo "仓库 $repo_name 更新失败"
        fi
        cd - || exit
    fi
    echo "仓库 $repo_name 处理完成"
}

# 遍历 REPOS 数组的键（即仓库 URL）
echo "开始遍历 REPOS 数组"
for repo in "${!REPOS[@]}"; do
    update_or_clone_repo "$repo"
done

echo -e "${GREEN}All repositories are up to date.${NC}"

cd $TARGET_DIR/turboacc/luci-app* && ls -la 
