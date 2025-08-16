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
if [ "$(grep -c "AXT-1800" $GITHUB_OUTPUT)" -eq '1' ] ;then
  # 定义kernel-6.12文件的路径
  KERNEL_FILE="./target/linux/generic/kernel-6.12"

  # 检查文件是否存在
  if [ ! -f "$KERNEL_FILE" ]; then
    echo "错误: 找不到文件 $KERNEL_FILE"
    exit 1
  fi

  # 提取主版本号
  MAJOR_VERSION=$(grep -oP 'LINUX_VERSION-\K[0-9.]+' "$KERNEL_FILE" | head -1)

  # 提取小版本号
  MINOR_VERSION=$(grep -oP 'LINUX_VERSION-[0-9.]+ = \K.[0-9]+' "$KERNEL_FILE" | head -1)

  # 组合完整版本号
  KERNEL_VERSION="${MAJOR_VERSION}${MINOR_VERSION}"

  # 验证版本号格式
  if [[ ! "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "错误: 无法提取有效的内核版本号"
    exit 1
  fi

  # 输出结果
  echo "提取的内核版本号: $KERNEL_VERSION"
  echo "你可以通过 \$KERNEL_VERSION 变量使用这个值"
  # sed -i '63s/0x1/0xf/;70s/0x1/0xf/' ./target/linux/qualcommax/patches-6.12/0054-v6.8-arm64-dts-qcom-ipq6018-use-CPUFreq-NVMEM.patch && echo "CPUFreq Done"
  wget -qO- "https://downloads.immortalwrt.org/snapshots/targets/qualcommax/ipq60xx/kmods/" | grep -oP "$KERNEL_VERSION-1-\K[0-9a-f]+" | head -n 1 > vermagic && echo "当前Vermagic:" && cat vermagic
  wget https://raw.githubusercontent.com/m0eak/openwrt_patch/refs/heads/main/gl-axt1800/9999-gl-axt1800-dts-change-cooling-level.patch && echo "下载成功" || echo "下载失败"
  mv 9999-gl-axt1800-dts-change-cooling-level.patch ./target/linux/qualcommax/patches-6.12/9999-gl-axt1800-dts-change-cooling-level.patch && echo "移动成功" || echo "移动失败"
  rm package/kernel/mac80211/patches/nss/ath11k/999-902-ath11k-fix-WDS-by-disabling-nwds.patch && echo "删除patch1成功" || echo "删除patch1失败（可能文件不存在）"
  rm package/kernel/mac80211/patches/nss/subsys/999-775-wifi-mac80211-Changes-for-WDS-MLD.patch && echo "删除patch2成功" || echo "删除patch2失败（可能文件不存在）"
  # rm package/kernel/mac80211/patches/nss/subsys/999-922-mac80211-fix-null-chanctx-warning-for-NSS-dynamic-VLAN.patch && echo "删除patch2成功" || echo "删除patch2失败（可能文件不存在）"
  if [ ! -s ./vermagic ]; then
    echo "none vermagic"
  else
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
  fi
fi
if [ "$(grep -c "x86" $GITHUB_OUTPUT)" -eq '1' ];then
  if [ "$(grep -c "immortalwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    rm -rf feeds/packages/lang/golang && echo "删除golang"
    git clone https://github.com/sbwml/packages_lang_golang -b 24.x feeds/packages/lang/golang
    cat feeds/packages/lang/golang/golang/Makefile
    sed -i "s/replace/$VERSION2/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.immortalwrt.org/releases/$VERSION2/targets/x86/64/immortalwrt-$VERSION2-x86-64.manifest | grep kernel | awk '{print $3}' | sed -E 's/.*~([0-9a-f]+)-r[0-9]+$/\1/; s/.*-([0-9a-f]+)$/\1/' > vermagic && echo "Immortalwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    #curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
    wget -P ./target/linux/generic/hack-6.6 https://raw.githubusercontent.com/chenmozhijin/turboacc/refs/heads/package/hack-6.6/952-add-net-conntrack-events-support-multiple-registrant.patch && echo "下载成功" || echo "下载失败"
    wget -P ./target/linux/generic/hack-6.6 https://raw.githubusercontent.com/chenmozhijin/turboacc/refs/heads/package/hack-6.6/953-net-patch-linux-kernel-to-support-shortcut-fe.patch && echo "下载成功" || echo "下载失败"
    git clone https://github.com/chenmozhijin/turboacc.git -b package ./package/turboacc-package
    cd ./package/turboacc-package && ls && find . -maxdepth 1 -type d ! -name 'shortcut-fe' && find . -maxdepth 1 -type d ! -name 'shortcut-fe' -exec rm -r {} +
    cd ../..   
    if [ ! -s ./vermagic ]; then
    echo "none vermagic"
    else
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    fi
  fi
  if [ "$(grep -c "Openwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    # 修补的firewall4、libnftnl、nftables与952补丁
    # curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
    sed -i "s/replace/$VERSION/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.openwrt.org/releases/$VERSION/targets/x86/64/openwrt-$VERSION-x86-64.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic && echo "Openwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages.git' >> feeds.conf.default
  fi
fi
if [ "$(grep -c "TR-3000" $GITHUB_OUTPUT)" -eq '1' ];then
  echo "TR-3000"
  # 调整cooling-levels
  # wget https://raw.githubusercontent.com/m0eak/openwrt_patch/main/mt3000/980-dts-mt7921-add-cooling-levels.patch 
  # mv 980-dts-mt7921-add-cooling-levels.patch ./target/linux/mediatek/patches-5.15/980-dts-mt7921-add-cooling-levels.patch 
  # rm -rf feeds/packages/lang/golang
  # git clone https://github.com/sbwml/packages_lang_golang -b 23.x feeds/packages/lang/golang
  # 固定内核版本值
  # curl -s https://downloads.immortalwrt.org/releases/$VERSION/targets/mediatek/filogic/immortalwrt-$VERSION-mediatek-filogic.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic && echo "MT3000 Vermagic Done" && echo "当前Vermagic：" && cat vermagic
  # sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
  # sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
fi
