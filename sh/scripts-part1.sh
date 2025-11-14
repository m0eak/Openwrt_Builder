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

# Uncomment a feed source
#sed -i 's/^#\(.*helloworld\)/\1/' feeds.conf.default

# Add a feed source
# echo 'src-git helloworld https://github.com/fw876/helloworld' >>feeds.conf.default
echo $TAG
echo $TAG2
echo $KERNEL_NAME
KERNEL=${KERNEL_NAME#k} && echo "当前Kernel：$KERNEL"
VERSION=${TAG#v} && echo "op当前版本：$VERSION"
VERSION2=${TAG2#v} && echo "imm当前版本：$VERSION2"
cat $GITHUB_OUTPUT
if [[ "$(grep -c "AXT-1800" $GITHUB_OUTPUT)" -eq 1 || "$(grep -c "JDC-AX6600" $GITHUB_OUTPUT)" -eq 1 ]]; then
  
  #修改tailscale
  sed -i '/\/etc\/init\.d\/tailscale/d;/\/etc\/config\/tailscale/d;' feeds/packages/net/tailscale/Makefile || echo "tailscale修改完成"

  # 定义kernel-6.12文件的路径
  KERNEL_FILE="./target/linux/generic/kernel-6.12"
  cat $KERNEL_FILE
  
  # 检查文件是否存在
  if [ ! -f "$KERNEL_FILE" ]; then
    echo "错误: 找不到文件 $KERNEL_FILE"
    exit 1
  fi

  ## 提取内核版本号
  MAJOR_VERSION=$(grep -oP 'LINUX_VERSION-\K[0-9.]+' "$KERNEL_FILE" | head -1)
  MINOR_VERSION=$(grep -oP 'LINUX_VERSION-[0-9.]+ = \K.[0-9]+' "$KERNEL_FILE" | head -1)
  KERNEL_VERSION="${MAJOR_VERSION}${MINOR_VERSION}"

  # 验证版本号格式
  if [[ ! "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "错误: 无法提取有效的内核版本号"
  fi

  # 输出结果
  echo "提取的内核版本号: $KERNEL_VERSION"

  #修改默认IP
  if [ "$(grep -c "AXT-1800" $GITHUB_OUTPUT)" -eq '1' ];then
    sed -i 's/192.168.1.1/192.168.8.1/g' package/base-files/files/bin/config_generate
  fi
  if [ "$(grep -c "JDC-AX6600" $GITHUB_OUTPUT)" -eq '1' ];then
    sed -i 's/192.168.1.1/192.168.10.1/g' package/base-files/files/bin/config_generate
  fi

  
  #更新Golang版本
  rm -rf feeds/packages/lang/golang && echo "删除golang"
  git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang

  ##下载对应内核版本的vermagic
  wget -qO- "https://downloads.immortalwrt.org/snapshots/targets/qualcommax/ipq60xx/kmods/" | grep -oP "$KERNEL_VERSION-1-\K[0-9a-f]+" | head -n 1 > vermagic && echo "当前Vermagic:" && cat vermagic
  wget https://raw.githubusercontent.com/m0eak/openwrt_patch/refs/heads/main/gl-axt1800/9999-gl-axt1800-dts-change-cooling-level.patch && echo "下载成功" || echo "下载失败"
  mv 9999-gl-axt1800-dts-change-cooling-level.patch ./target/linux/qualcommax/patches-6.12/9999-gl-axt1800-dts-change-cooling-level.patch && echo "移动成功" || echo "移动失败"
  rm package/kernel/mac80211/patches/nss/ath11k/999-902-ath11k-fix-WDS-by-disabling-nwds.patch && echo "删除patch1成功" || echo "删除patch1失败（可能文件不存在）"
  rm package/kernel/mac80211/patches/nss/subsys/999-775-wifi-mac80211-Changes-for-WDS-MLD.patch && echo "删除patch2成功" || echo "删除patch2失败（可能文件不存在）"

  ##修改vermagic
  if [ ! -s ./vermagic ]; then
    echo "none vermagic"
  else
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
  fi
fi

if [ "$(grep -c "x86" $GITHUB_OUTPUT)" -eq '1' ];then
  if [ "$(grep -c "immortalwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    #更新Golang版本
    rm -rf feeds/packages/lang/golang && echo "删除golang"
    git clone https://github.com/sbwml/packages_lang_golang -b 25.x feeds/packages/lang/golang
    cat feeds/packages/lang/golang/golang/Makefile

    #修改默认IP
    sed -i 's/192.168.1.1/192.168.100.1/g' package/base-files/files/bin/config_generate
    ##修改版本号
    sed -i "s/replace/$VERSION2/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"

    ##下载对应内核版本的vermagic
    curl -s https://downloads.immortalwrt.org/releases/$VERSION2/targets/x86/64/immortalwrt-$VERSION2-x86-64.manifest | grep kernel | awk '{print $3}' | sed -E 's/.*~([0-9a-f]+)-r[0-9]+$/\1/; s/.*-([0-9a-f]+)$/\1/' > vermagic && echo "Immortalwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk

    ##修改vermagic
    if [ ! -s ./vermagic ]; then
    echo "none vermagic"
    else
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    fi
  fi
fi
if [ "$(grep -c "TR-3000" $GITHUB_OUTPUT)" -eq '1' ];then
  echo "TR-3000"
  sed -i 's/192.168.6.1/192.168.100.209/g' package/base-files/files/bin/config_generate
fi
