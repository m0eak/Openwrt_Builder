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
# rm -rf feeds.conf.default
# touch feeds.conf.default
echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages' >>feeds.conf.default
echo 'src-git small https://github.com/kenzok8/small' >>feeds.conf.default
echo 'src-git smoothwan https://github.com/SmoothWAN/SmoothWAN-feeds' >>feeds.conf.default
# fix cpu_opp_table
sed -i '43s/0x3/0xf/;50s/0x3/0xf/;57s/0x1/0xf/' target/linux/qualcommax/patches-6.1/0154-arm64-dts-qcom-ipq6018-use-CPUFreq-NVMEM.patch

