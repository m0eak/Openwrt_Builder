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
echo 'src-git small https://github.com/kenzok8/small' >>feeds.conf.default
echo 'src-git linkease_nas https://github.com/linkease/nas-packages-luci' >>feeds.conf.default
echo 'src-git linkease_nas_package https://github.com/linkease/nas-packages.git' >>feeds.conf.default
echo 'src-git istore https://github.com/linkease/istore.git' >>feeds.conf.default
# echo 'src-git kenzok https://github.com/kenzok8/small-package.git' >>feeds.conf.default
curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
