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
rm -rf feeds.conf.default
touch feeds.conf.default
echo 'src-git packages https://git.openwrt.org/feed/packages.git' >>feeds.conf.default
echo 'src-git luci https://git.openwrt.org/project/luci.git' >>feeds.conf.default
echo 'src-git routing https://git.openwrt.org/feed/routing.git' >>feeds.conf.default
echo 'src-git telephony https://git.openwrt.org/feed/telephony.git' >>feeds.conf.default
echo 'src-git nss_packages https://github.com/qosmio/nss-packages.git' >>feeds.conf.default
# echo 'src-git sqm_scripts_nss https://github.com/qosmio/sqm-scripts-nss.git' >>feeds.conf.default
# echo 'src-git mosdns https://github.com/sbwml/luci-app-mosdns' >>feeds.conf.default
git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/bin/config_generate && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/etc/banner && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 include/version.mk && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/network/config/wifi-scripts/files/lib/wifi/mac80211.sh && echo "Done"
echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >>feeds.conf.default
echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages' >>feeds.conf.default
echo 'src-git small https://github.com/kenzok8/small' >>feeds.conf.default
echo 'src-git smoothwan https://github.com/SmoothWAN/SmoothWAN-feeds' >>feeds.conf.default
# curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
# fix cpu_opp_table
sed -i '49s/0x3/0xf/;56s/0x3/0xf/;63s/0x1/0xf/;70s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0054-v6.8-arm64-dts-qcom-ipq6018-use-CPUFreq-NVMEM.patch
sed -i '39s/0x3/0xf/;47s/0x3/0xf/;55s/0x1/0xf/;63s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0910-arm64-dts-qcom-ipq6018-change-voltage-to-perf-levels.patch
