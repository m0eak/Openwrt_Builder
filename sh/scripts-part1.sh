#!/bin/bash
#
# Copyright (c) 2019-2020 P3TERX <https://p3terx.com>
#
# This is free software, licensed under the MIT License.
# See /LICENSE for more information.
#
# https://github.com/P3TERX/Actions-OpenWrt
# File name: diy-part1.sh
# Description: OpenWrt DIY script part 1 (Before Update feeds)
#

# --- 调试信息：打印所有可能用到的环境变量 ---
echo "--- 脚本开始执行，正在检查环境变量喵～ ---"
echo "WORKFLOW_NAME: $WORKFLOW_NAME" # 这是最重要的判断依据！
echo "TAG (from libwrt): $TAG"
echo "TAG2 (from immortalwrt): $TAG2"
# KERNEL_NAME 在所有工作流中都未定义，所以注释掉相关逻辑
# echo "KERNEL_NAME: $KERNEL_NAME"
echo "------------------------------------------"

# --- 根据 WORKFLOW_NAME 执行不同的逻辑 ---

# --- 逻辑块 1: 处理 AXT-1800 和 JDC-AX6600 ---
if [[ "$WORKFLOW_NAME" == "AXT-1800" || "$WORKFLOW_NAME" == "JDC-AX6600" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 libwrt 的特定修改喵～"

    # 修改tailscale
    ls ./feeds/packages/net/tailscale/
    sed -i '/\/etc\/init\.d\/tailscale/d;/\/etc\/config\/tailscale/d;' ./feeds/packages/net/tailscale/Makefile && echo "tailscale修改完成"

    # 定义kernel-6.12文件的路径
    KERNEL_FILE="./target/linux/generic/kernel-6.12"
    cat $KERNEL_FILE
    
    # 检查文件是否存在
    if [ ! -f "$KERNEL_FILE" ]; then
        echo "错误: 找不到文件 $KERNEL_FILE"
        exit 1
    fi

    # 提取内核版本号
    MAJOR_VERSION=$(grep -oP 'LINUX_VERSION-\K[0-9.]+' "$KERNEL_FILE" | head -1)
    MINOR_VERSION=$(grep -oP 'LINUX_VERSION-[0-9.]+ = \K.[0-9]+' "$KERNEL_FILE" | head -1)
    KERNEL_VERSION="${MAJOR_VERSION}${MINOR_VERSION}"

    # 验证版本号格式
    if [[ ! "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "错误: 无法提取有效的内核版本号"
    fi
    echo "提取的内核版本号: $KERNEL_VERSION"

    # 修改默认IP
    if [[ "$WORKFLOW_NAME" == "AXT-1800" ]]; then
        sed -i 's/192.168.1.1/192.168.8.1/g' package/base-files/files/bin/config_generate
        echo "AXT-1800 IP 修改为 192.168.8.1"
    elif [[ "$WORKFLOW_NAME" == "JDC-AX6600" ]]; then
        sed -i 's/192.168.1.1/192.168.100.1/g' package/base-files/files/bin/config_generate
        echo "JDC-AX6600 IP 修改为 192.168.100.1"
    fi

    # 更新Golang版本
    rm -rf feeds/packages/lang/golang && echo "删除golang"
    git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang

    # 下载对应内核版本的vermagic
    wget -qO- "https://downloads.immortalwrt.org/snapshots/targets/qualcommax/ipq60xx/kmods/" | grep -oP "$KERNEL_VERSION-1-\K[0-9a-f]+" | head -n 1 > vermagic && echo "当前Vermagic:" && cat vermagic
    wget https://raw.githubusercontent.com/m0eak/openwrt_patch/refs/heads/main/gl-axt1800/9999-gl-axt1800-dts-change-cooling-level.patch && echo "下载成功" || echo "下载失败"
    mv 9999-gl-axt1800-dts-change-cooling-level.patch ./target/linux/qualcommax/patches-6.12/9999-gl-axt1800-dts-change-cooling-level.patch && echo "移动成功" || echo "移动失败"
    rm -f package/kernel/mac80211/patches/nss/ath11k/999-902-ath11k-fix-WDS-by-disabling-nwds.patch && echo "删除patch1成功"
    rm -f package/kernel/mac80211/patches/nss/subsys/999-775-wifi-mac80211-Changes-for-WDS-MLD.patch && echo "删除patch2成功"

    VERMAGIC=$(cat vermagic)
    echo "VERMAGIC_FIX=${VERMAGIC}" >> $GITHUB_ENV

    # 修改vermagic
    if [ ! -s ./vermagic ]; then
        echo "none vermagic"
    else
        sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
        sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    fi

# --- 逻辑块 2: 处理 x86 immortalwrt ---
elif [[ "$WORKFLOW_NAME" == "x86_immortalwrt" ]]; then
    echo ">>> 检测到: $WORKFLOW_NAME。开始执行 x86 immortalwrt 的特定修改喵～"
    
    # immortalwrt 工作流定义了 TAG2，所以 VERSION2 现在是有效的！
    VERSION2=${TAG2#v}
    echo "immortalwrt 当前版本 (VERSION2): $VERSION2"

    # 更新Golang版本
    rm -rf feeds/packages/lang/golang && echo "删除golang"
    git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang
    cat feeds/packages/lang/golang/golang/Makefile

    # 修改默认IP
    sed -i 's/192.168.1.1/192.168.100.1/g' package/base-files/files/bin/config_generate
    echo "x86 IP 修改为 192.168.100.1"

    # 修改版本号
    if [ -n "$VERSION2" ]; then
        sed -i "s/replace/$VERSION2/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    else
        echo "警告: VERSION2 为空，跳过版本号替换。"
    fi

    # 下载对应内核版本的vermagic
    if [ -n "$VERSION2" ]; then
        curl -s "https://downloads.immortalwrt.org/releases/$VERSION2/targets/x86/64/immortalwrt-$VERSION2-x86-64.manifest" | grep kernel | awk '{print $3}' | sed -E 's/.*~([0-9a-f]+)-r[0-9]+$/\1/; s/.*-([0-9a-f]+)$/\1/' > vermagic && echo "Immortalwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    else
        echo "警告: VERSION2 为空，无法下载 vermagic。"
    fi

    # 修改vermagic
    if [ -s ./vermagic ]; then
        sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
        sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    else
        echo "none vermagic, 跳过修改。"
    fi

# --- 逻辑块 3: 处理 TR-3000 ---
elif [[ "$WORKFLOW_NAME" == "TR-3000" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 TR-3000 的特定修改喵～"
    sed -i 's/192.168.6.1/192.168.100.209/g' package/base-files/files/bin/config_generate
    echo "TR-3000 IP 修改为 192.168.100.209"

else
    echo ">>> 未匹配到任何已知的 WORKFLOW_NAME ('$WORKFLOW_NAME')。跳过所有设备特定的修改喵～"
fi

echo "--- DIY Part 1 脚本执行完毕喵～ ---"