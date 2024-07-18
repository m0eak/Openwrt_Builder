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
VERSION=${TAG#v} && echo "当前版本：" && echo $VERSION
echo $GITHUB_OUTPUT
echo $GITHUB_ENV


if [ "$(grep -c "AXT-1800" $GITHUB_OUTPUT)" -eq '1' ] ;then
  rm -rf feeds.conf.default
  touch feeds.conf.default
  echo 'src-git packages https://git.openwrt.org/feed/packages.git' >> feeds.conf.default
  echo 'src-git luci https://git.openwrt.org/project/luci.git' >> feeds.conf.default
  echo 'src-git routing https://git.openwrt.org/feed/routing.git' >> feeds.conf.default
  echo 'src-git telephony https://git.openwrt.org/feed/telephony.git' >> feeds.conf.default
  echo 'src-git nss_packages https://github.com/qosmio/nss-packages.git;NSS-12.5-K6.x' >> feeds.conf.default
  echo 'src-git sqm_scripts_nss https://github.com/qosmio/sqm-scripts-nss.git' >> feeds.conf.default
  echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >> feeds.conf.default
  echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages' >> feeds.conf.default
  echo 'src-git small https://github.com/kenzok8/small' >> feeds.conf.default
  git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/bin/config_generate && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/etc/banner && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 include/version.mk && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/network/config/wifi-scripts/files/lib/wifi/mac80211.sh && echo "Done"
  echo "26768f9df0f6231779971745d5152147" > vermagic && echo "vermagic done"
  sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
  sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
  # sed -i '49s/0x3/0xf/;56s/0x3/0xf/;63s/0x1/0xf/;70s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0054-v6.8-arm64-dts-qcom-ipq6018-use-CPUFreq-NVMEM.patch
  # sed -i '39s/0x3/0xf/;47s/0x3/0xf/;55s/0x1/0xf/;63s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0910-arm64-dts-qcom-ipq6018-change-voltage-to-perf-levels.patch
  # sed -i 's/16384/65536/g' ./package/kernel/linux/files/sysctl-nf-conntrack.conf
fi
if [ "$(grep -c "x86" $GITHUB_OUTPUT)" -eq '1' ];then
  if [ "$(grep -c "immortalwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    sed -i "s/replace/$VERSION/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.immortalwrt.org/releases/$VERSION/targets/x86/64/immortalwrt-$VERSION-x86-64.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic 
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    echo "Immortalwrt Vermagic Done"
  fi
  if [ "$(grep -c "Openwrt" $GITHUB_OUTPUT)" -eq '1' ];then
    # 修补的firewall4、libnftnl、nftables与952补丁
    # curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
    sed -i "s/replace/$VERSION/g" $GITHUB_WORKSPACE/files/etc/uci-defaults/zzz_m0eak && echo "VERSION替换成功"
    curl -s https://downloads.openwrt.org/releases/$VERSION/targets/x86/64/openwrt-$VERSION-x86-64.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic
    sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
    sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
    echo "Openwrt Vermagic Done"
  fi
  echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages.git' >> feeds.conf.default
fi
if [ "$(grep -c "MT-3000" $GITHUB_OUTPUT)" -eq '1' ];then
  echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >> feeds.conf.default
  # 修补的firewall4、libnftnl、nftables与952补丁
  curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
  # 调整cooling-levels
  wget https://raw.githubusercontent.com/m0eak/openwrt_patch/main/mt3000/980-dts-mt7921-add-cooling-levels.patch 
  mv 980-dts-mt7921-add-cooling-levels.patch ./target/linux/mediatek/patches-5.15/980-dts-mt7921-add-cooling-levels.patch 
  # 固定内核版本值
  curl -s https://downloads.immortalwrt.org/releases/$VERSION/targets/mediatek/filogic/immortalwrt-$VERSION-mediatek-filogic.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic
  sed -i '/grep '\''=\[ym\]'\'' $(LINUX_DIR)\/\.config\.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)\/\.vermagic/s/^/# /' ./include/kernel-defaults.mk
  sed -i '/$(LINUX_DIR)\/\.vermagic/a \\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic' ./include/kernel-defaults.mk
fi



