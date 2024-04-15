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
# 添加自定义feeds
echo "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git" >>feeds.conf.default
# 修补的firewall4、libnftnl、nftables与952补丁
curl -sSL https://raw.githubusercontent.com/chenmozhijin/turboacc/luci/add_turboacc.sh -o add_turboacc.sh && bash add_turboacc.sh
# 调整cooling-levels
wget https://raw.githubusercontent.com/m0eak/openwrt_patch/main/mt3000/980-dts-mt7921-add-cooling-levels.patch 
mv 980-dts-mt7921-add-cooling-levels.patch ./target/linux/mediatek/patches-5.15/980-dts-mt7921-add-cooling-levels.patch 
# 固定内核版本值
echo "317eb6a6d9828371f8f0ca9cfaff251a" >> vermagic
sed -i '121s|.*|        cp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic|' ./include/kernel-defaults.mk
# sed -i '/^grep \'\=[ym]\' \$(LINUX_DIR)\/\.config\.set \| LC_ALL=C sort \| \$(MKHASH) md5 > \$(LINUX_DIR)\/\.vermagic$/c\cp \$(TOPDIR)\/vermagic \$(LINUX_DIR)\/.vermagic' ./include/kernel-defaults.mk
# sed -i '121s|grep '\''=[ym]'\'' $(LINUX_DIR)/.config.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)/.vermagic|cp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic|' ./include/kernel-defaults.mk
# sed -i '121s#grep '\''=[ym]'\'' $(LINUX_DIR)/.config.set | LC_ALL=C sort | $(MKHASH) md5 > $(LINUX_DIR)/.vermagic#cp $(TOPDIR)/vermagic $(LINUX_DIR)/.vermagic#' ./include/kernel-defaults.mk
# curl -s https://downloads.immortalwrt.org/releases/23.05.2/targets/mediatek/filogic/immortalwrt-23.05.2-mediatek-filogic.manifest | grep kernel | awk '{print $3}' | awk -F- '{print $3}' > vermagic

