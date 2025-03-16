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
  wget -qO- "https://downloads.immortalwrt.org/snapshots/targets/qualcommax/ipq807x/kmods/" | grep -oP "$KERNEL-1-\K[0-9a-f]+" | head -n 1 > vermagic && echo "当前Vermagic:" && cat vermagic
  if [ ! -s ./vermagic ]; then
    echo "none"
  else
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
  fi
fi
if [ "$(grep -c "x86" $GITHUB_OUTPUT)" -eq '1' ];then
  if [ "$(grep -c "immortalwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    sed -i "s/replace/$VERSION2/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.immortalwrt.org/releases/$VERSION2/targets/x86/64/immortalwrt-$VERSION2-x86-64.manifest | grep kernel | awk '{print $3}' | sed -E 's/.*~([0-9a-f]+)-r[0-9]+$/\1/; s/.*-([0-9a-f]+)$/\1/' > vermagic && echo "Immortalwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    # curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
  fi
  if [ "$(grep -c "Openwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    # 修补的firewall4、libnftnl、nftables与952补丁
    curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
    sed -i "s/replace/$VERSION/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.openwrt.org/releases/$VERSION/targets/x86/64/openwrt-$VERSION-x86-64.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic && echo "Openwrt Vermagic Done" && echo "当前Vermagic：" && cat vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages.git' >> feeds.conf.default
  fi
fi
if [ "$(grep -c "MT-3000" $GITHUB_OUTPUT)" -eq '1' ];then
  # echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >> feeds.conf.default
  # 修补的firewall4、libnftnl、nftables与952补丁
  # 调整cooling-levels
  wget https://raw.githubusercontent.com/m0eak/openwrt_patch/main/mt3000/980-dts-mt7921-add-cooling-levels.patch 
  mv 980-dts-mt7921-add-cooling-levels.patch ./target/linux/mediatek/patches-5.15/980-dts-mt7921-add-cooling-levels.patch 
  rm -rf feeds/packages/lang/golang
  git clone https://github.com/sbwml/packages_lang_golang -b 23.x feeds/packages/lang/golang
  # 固定内核版本值
  # curl -s https://downloads.immortalwrt.org/releases/$VERSION/targets/mediatek/filogic/immortalwrt-$VERSION-mediatek-filogic.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic && echo "MT3000 Vermagic Done" && echo "当前Vermagic：" && cat vermagic
  # sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
  # sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
fi
