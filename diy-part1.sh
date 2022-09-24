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
#echo 'src-git helloworld https://github.com/fw876/helloworld' >>feeds.conf.default
rm -rf feeds.conf.default
touch feeds.conf.default
echo 'src-git packages https://github.com/zheshifandian/packages.git;axt1800' >>feeds.conf.default
echo 'src-git routing https://github.com/openwrt/routing.git;openwrt-19.07' >>feeds.conf.default
echo 'src-git telephony https://github.com/openwrt/telephony.git;openwrt-21.02' >>feeds.conf.default
echo 'src-git openclash https://github.com/vernesong/OpenClash.git' >>feeds.conf.default
echo 'src-git luci https://github.com/zheshifandian/luci.git;axt1800' >>feeds.conf.default
echo 'src-git kenzo https://github.com/kenzok8/openwrt-packages' >>feeds.conf.default
echo 'src-git small https://github.com/kenzok8/small' >>feeds.conf.default
echo 'src-git homeproxy https://github.com/immortalwrt/homeproxy' >>feeds.conf.default
