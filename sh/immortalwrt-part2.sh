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
sed -i 's/192.168.1.1/192.168.100.1/g' package/base-files/files/bin/config_generate
# Modify Openwrt to AXT1800
# sed -i 's/'OpenWrt'/'GL-AXT1800'/g' package/base-files/files/bin/config_generate
find ./ | grep Makefile | grep v2ray-geodata | xargs rm -f
find ./ | grep Makefile | grep mosdns | xargs rm -f
find ./ | grep Makefile | grep openclash | xargs rm -f
find ./ | grep Makefile | grep ddns-go | xargs rm -f
# find ./ | grep Makefile | grep homeproxy | xargs rm -f
# find ./ | grep Makefile | grep tailscale | xargs rm -f

git clone --depth 1 https://github.com/sbwml/luci-app-mosdns -b v5 package/mosdns
git clone --depth 1 https://github.com/sbwml/v2ray-geodata package/v2ray-geodata
git clone --depth 1 https://github.com/vernesong/OpenClash.git package/openclash
git clone --depth 1 https://github.com/sirpdboy/luci-app-ddns-go.git package/ddns-go
# git clone --depth 1 https://github.com/bulianglin/homeproxy.git package/luci-app-homeproxy
# Update Tailscale
git clone https://github.com/asvow/luci-app-tailscale package/luci-app-tailscale
sed -i '/\/etc\/init\.d\/tailscale/d;/\/etc\/config\/tailscale/d;' openwrt/feeds/packages/net/tailscale/Makefile && echo "tailscale修复更新成功"
./scripts/feeds install -a
