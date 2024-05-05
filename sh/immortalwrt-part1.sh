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
# sed -i 's/^#\(.*helloworld\)/\1/' feeds.conf.default

# Add a feed source
# echo 'src-git helloworld https://github.com/fw876/helloworld' >>feeds.conf.default
# rm -rf feeds.conf.default
# touch feeds.conf.default
# echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages' >>feeds.conf.default
echo 'src-git small https://github.com/kenzok8/small-package' >>feeds.conf.default
# echo 'src-git kiddin9 https://github.com/kiddin9/openwrt-packages.git' >>feeds.conf.default
# echo 'src-git linkease_nas https://github.com/linkease/nas-packages-luci' >>feeds.conf.default
# echo 'src-git linkease_nas_package https://github.com/linkease/nas-packages.git' >>feeds.conf.default
# echo 'src-git istore https://github.com/linkease/istore.git' >>feeds.conf.default
# echo 'src-git kenzok https://github.com/kenzok8/small-package.git' >>feeds.conf.default
# curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
# 固定内核版本值
# curl -s https://downloads.immortalwrt.org/releases/23.05.2/targets/x86/64/immortalwrt-23.05.2-x86-64.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic
wget https://downloads.immortalwrt.org/releases/23.05.2/targets/x86/64/immortalwrt-23.05.2-x86-64.manifest
grep kernel immortalwrt*.manifest | awk '{print $3}' | awk -F- '{print $3}' > vermagic
# echo "317eb6a6d9828371f8f0ca9cfaff251a" > vermagic
sed -i '121s|^|# |' ./include/kernel-defaults.mk
sed -i $'121a\\\tcp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic\\' ./include/kernel-defaults.mk
