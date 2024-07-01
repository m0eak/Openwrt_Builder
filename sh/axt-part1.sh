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
echo 'src-git packages https://github.com/immortalwrt/packages.git^fc5c6d19bc1e63affa36dc2d9107873469f96311' >>feeds.conf.default
echo 'src-git luci https://github.com/immortalwrt/luci.git^7ce5799365f2ba329825a169b507718359303191' >>feeds.conf.default
echo 'src-git routing https://github.com/openwrt/routing.git^0617824a44f037f68dfa80be25693bf5bc6f4ce5' >>feeds.conf.default
echo 'src-git telephony https://github.com/openwrt/telephony.git^86af194d03592121f5321474ec9918dd109d3057' >>feeds.conf.default
echo 'src-git nss_packages https://github.com/qosmio/nss-packages.git;NSS-12.5-K6.x-NAPI' >>feeds.conf.default
echo 'src-git sqm_scripts_nss https://github.com/qosmio/sqm-scripts-nss.git' >>feeds.conf.default
# echo 'src-git mosdns https://github.com/sbwml/luci-app-mosdns' >>feeds.conf.default
git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/bin/config_generate && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/base-files/files/etc/banner && git checkout 0bd5323b7ad9e523584a156a0bd83881c4dea910 package/network/config/wifi-scripts/files/lib/wifi/mac80211.sh && echo "Done"
echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >>feeds.conf.default
echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages' >>feeds.conf.default
echo 'src-git small https://github.com/kenzok8/small' >>feeds.conf.default
echo 'src-git smoothwan https://github.com/SmoothWAN/SmoothWAN-feeds' >>feeds.conf.default
# fix cpu_opp_table
sed -i '49s/0x3/0xf/;56s/0x3/0xf/;63s/0x1/0xf/;70s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0054-v6.8-arm64-dts-qcom-ipq6018-use-CPUFreq-NVMEM.patch
sed -i '39s/0x3/0xf/;47s/0x3/0xf/;55s/0x1/0xf/;63s/0x1/0xf/' ./target/linux/qualcommax/patches-6.6/0910-arm64-dts-qcom-ipq6018-change-voltage-to-perf-levels.patch
