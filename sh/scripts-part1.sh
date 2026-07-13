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
echo "--- 脚本开始执行，正在检查环境变量 ---"
echo "WORKFLOW_NAME: $WORKFLOW_NAME" # 这是最重要的判断依据！
echo "TAG (from libwrt): $TAG"
echo "TAG2 (from immortalwrt): $TAG2"
echo "------------------------------------------"

set_default_ip() {
    local ip="$1"
    local label="$2"

    sed -i "s/192.168.1.1/$ip/g" package/base-files/files/bin/config_generate
    echo "$label IP 修改为 $ip"
}

# --- 根据 WORKFLOW_NAME 执行不同的逻辑 ---

# --- 逻辑块 1: 处理 AXT-1800 和 JDC-AX6600 ---
if [[ "$WORKFLOW_NAME" == "AXT-1800" || "$WORKFLOW_NAME" == "JDC-AX6600" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 libwrt 的特定修改"

    # 修改默认IP
    if [[ "$WORKFLOW_NAME" == "AXT-1800" ]]; then
        set_default_ip "192.168.8.1" "AXT-1800"
    elif [[ "$WORKFLOW_NAME" == "JDC-AX6600" ]]; then
        set_default_ip "192.168.100.1" "JDC-AX6600"
    fi

    # 更新Golang版本（当前已停用，保留注释便于回滚）
    # rm -rf feeds/packages/lang/golang && echo "删除golang"
    # git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang

    wget https://raw.githubusercontent.com/m0eak/openwrt_patch/refs/heads/main/gl-axt1800/9999-gl-axt1800-dts-change-cooling-level.patch && echo "下载成功" || echo "下载失败"
    mv 9999-gl-axt1800-dts-change-cooling-level.patch ./target/linux/qualcommax/patches-6.12/9999-gl-axt1800-dts-change-cooling-level.patch && echo "移动成功" || echo "移动失败"
    rm -f package/kernel/mac80211/patches/nss/ath11k/999-902-ath11k-fix-WDS-by-disabling-nwds.patch && echo "删除patch1成功"
    rm -f package/kernel/mac80211/patches/nss/subsys/999-775-wifi-mac80211-Changes-for-WDS-MLD.patch && echo "删除patch2成功"

# --- 逻辑块 2: 处理 x86 immortalwrt ---
elif [[ "$WORKFLOW_NAME" == "x86_immortalwrt" ]]; then
    echo ">>> 检测到: $WORKFLOW_NAME。开始执行 x86 immortalwrt 的特定修改"
    
    # immortalwrt 工作流定义了 TAG2，所以 VERSION2 现在是有效的！
    VERSION2=${TAG2#v}
    echo "immortalwrt 当前版本 (VERSION2): $VERSION2"

    # 更新Golang版本（当前已停用，保留注释便于回滚）
    # rm -rf feeds/packages/lang/golang && echo "删除golang"
    # git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang
    # cat feeds/packages/lang/golang/golang/Makefile

    # 修改默认IP
    set_default_ip "192.168.100.1" "x86"

    # 修改版本号
    if [ -n "$VERSION2" ]; then
        sed -i "s/replace/$VERSION2/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    else
        echo "警告: VERSION2 为空，跳过版本号替换。"
    fi

# --- 逻辑块 3: 处理 TR-3000 ---
elif [[ "$WORKFLOW_NAME" == "TR-3000" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 TR-3000 的特定修改"
    #sed -i 's/192.168.6.1/192.168.100.209/g' package/base-files/files/bin/config_generate
    #echo "TR-3000 IP 修改为 192.168.100.209"

# --- 逻辑块 4: 处理 GL-MT3600BE ---
elif [[ "$WORKFLOW_NAME" == "GL-MT3600BE" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 MT3600BE 的特定修改"

    CUSTOM_DTS_URL="https://raw.githubusercontent.com/openwrt/openwrt/cced8d95f3caa9f48eaeb4ef2d15426d20afaf16/target/linux/mediatek/dts/mt7987a-glinet-gl-mt3600be.dts"
    CUSTOM_DTS_TARGET="target/linux/mediatek/dts/mt7987a-glinet-gl-mt3600be.dts"
    CUSTOM_DTS_TMP="/tmp/mt7987a-glinet-gl-mt3600be.dts"

    if [[ -f "$CUSTOM_DTS_TARGET" ]]; then
        echo "开始下载自定义 MT3600BE DTS..."
        curl -fL "$CUSTOM_DTS_URL" -o "$CUSTOM_DTS_TMP"

        echo "校验下载到的 DTS..."
        grep -q 'GL-MT3600BE' "$CUSTOM_DTS_TMP"
        grep -q 'cooling-levels' "$CUSTOM_DTS_TMP"

        cp "$CUSTOM_DTS_TMP" "$CUSTOM_DTS_TARGET"
        echo "已替换 $CUSTOM_DTS_TARGET"
        echo "cooling-levels 片段:"
        grep -n 'cooling-levels' "$CUSTOM_DTS_TARGET"
    else
        echo "错误: 未找到目标 DTS 文件 $CUSTOM_DTS_TARGET"
        exit 1
    fi

    set_default_ip "192.168.9.1" "mt3600be"

# --- 逻辑块 5: 处理 GL-MT5000 ---
elif [[ "$WORKFLOW_NAME" == "GL-MT5000" ]]; then
    echo ">>> 检测到设备: $WORKFLOW_NAME。开始执行 MT5000 的特定修改"
    set_default_ip "192.168.100.1" "mt5000"

else
    echo ">>> 未匹配到任何已知的 WORKFLOW_NAME ('$WORKFLOW_NAME')。跳过所有设备特定的修改"
fi

echo "--- DIY Part 1 脚本执行完毕 ---"
