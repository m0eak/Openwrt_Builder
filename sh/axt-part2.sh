#!/bin/bash
#
# Copyright (c) 2019-2020 P3TERX <https://p3terx.com>
#
# This is free software, licensed under the MIT License.
# See /LICENSE for more information.
#
# https://github.com/P3TERX/Actions-OpenWrt
# File name: diy-part2.sh
# Description: OpenWrt DIY script part 2 (After Update feeds)
#

# Modify default IP
sed -i 's/192.168.1.1/192.168.8.1/g' ./package/base-files/files/bin/config_generate
# Modify Openwrt to AXT1800
sed -i 's/'OpenWrt'/'GL-AXT1800'/g' ./package/base-files/files/bin/config_generate
find ./ | grep Makefile | grep v2ray-geodata | xargs rm -f
find ./ | grep Makefile | grep mosdns | xargs rm -f
find ./ | grep Makefile | grep app-store | xargs rm -f
find ./ | grep Makefile | grep linkease | xargs rm -f
find ./ | grep Makefile | grep linkmount | xargs rm -f
find ./ | grep Makefile | grep quickstart | xargs rm -f
find ./ | grep Makefile | grep unishare | xargs rm -f
find ./ | grep Makefile | grep webdav2 | xargs rm -f
find ./ | grep Makefile | grep turboacc | xargs rm -f
git clone --depth=1 https://github.com/sbwml/luci-app-mosdns -b v5 package/mosdns
git clone --depth=1 https://github.com/sbwml/v2ray-geodata package/v2ray-geodata
git clone --depth=1 https://github.com/linkease/istore.git package/istore
git clone --depth=1 https://github.com/linkease/nas-packages-luci.git package/nas-packages-luci
git clone --depth=1 https://github.com/linkease/nas-packages.git package/nas-packages
git clone --depth=1 https://github.com/asvow/luci-app-tailscale package/luci-app-tailscale
git clone --depth=1 https://github.com/chenmozhijin/turboacc.git package/turboacc
mkdir ./package/custom
# git clone -b NSS-12.5-K6.x-NAPI https://github.com/qosmio/nss-packages.git package/nss-packages
git clone https://github.com/sbwml/autocore-arm.git ./package/custom/
sed -i '/\/etc\/init\.d\/tailscale/d;/\/etc\/config\/tailscale/d;' feeds/packages/net/tailscale/Makefile
# cd ./package/nss-packages
# git checkout 7eb6a1e14deb6af0a41cce8d4fead519db583560
# ./scripts/feeds install -a

