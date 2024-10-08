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
find ./ | grep Makefile | grep v2ray-geodata | xargs rm -f
find ./ | grep Makefile | grep mosdns | xargs rm -f
find ./ | grep Makefile | grep openclash | xargs rm -f
find ./ | grep Makefile | grep ddns-go | xargs rm -f
find ./ | grep Makefile | grep homeproxy | xargs rm -f
find ./ | grep Makefile | grep wolplus | xargs rm -f
find ./ | grep Makefile | grep luci-theme-design | xargs rm -f
find ./ | grep Makefile | grep design-config | xargs rm -f
if [ "$(grep -c "AXT-1800" $GITHUB_OUTPUT)" -eq '1' ];then
  sed -i 's/192.168.1.1/192.168.8.1/g' ./package/base-files/files/bin/config_generate
  sed -i 's/'OpenWrt'/'GL-AXT1800'/g' ./package/base-files/files/bin/config_generate
  find ./ | grep Makefile | grep app-store | xargs rm -f
  find ./ | grep Makefile | grep linkease | xargs rm -f
  find ./ | grep Makefile | grep linkmount | xargs rm -f
  find ./ | grep Makefile | grep quickstart | xargs rm -f
  find ./ | grep Makefile | grep turboacc | xargs rm -f
  find ./ | grep Makefile | grep unishare | xargs rm -f
  find ./ | grep Makefile | grep webdav2 | xargs rm -f
  git clone --depth 1 https://github.com/linkease/istore.git package/istore
  git clone --depth 1 https://github.com/linkease/nas-packages-luci.git package/nas-packages-luci
  git clone --depth 1 https://github.com/linkease/nas-packages.git package/nas-packages
  git clone --depth 1 https://github.com/asvow/luci-app-tailscale package/luci-app-tailscale
  git clone --depth 1 https://github.com/chenmozhijin/turboacc.git package/turboacc
  # sed -i '/\/etc\/init\.d\/tailscale/d;/\/etc\/config\/tailscale/d;' feeds/packages/net/tailscale/Makefile
  echo "axt1800 part-2"
fi
if [ "$(grep -c "immortalwrt" $GITHUB_OUTPUT)" -eq '1' ];then
  # find ./ | grep Makefile | grep turboacc | xargs rm -f
  # git clone --depth 1 https://github.com/chenmozhijin/turboacc.git package/turboacc
  sed -i 's/192.168.1.1/192.168.100.1/g' package/base-files/files/bin/config_generate
  echo "immortalwrt part-2"
  rm -rf feeds/packages/lang/golang
  git clone https://github.com/sbwml/packages_lang_golang -b 22.x feeds/packages/lang/golang
fi
if [ "$(grep -c "Openwrt" $GITHUB_OUTPUT)" -eq '1' ];then
  sed -i 's/192.168.1.1/192.168.100.100/g' package/base-files/files/bin/config_generate
  echo "Openwrt part-2"
fi
if [ "$(grep -c "MT-3000" $GITHUB_OUTPUT)" -eq '1' ];then
  sed -i 's/192.168.1.1/192.168.8.1/g' ./package/base-files/files/bin/config_generate
  sed -i 's/'ImmortalWrt'/'GL-MT3000'/g' ./package/base-files/files/bin/config_generate
  echo "MT3000 part-2"
fi
git clone --depth 1 https://github.com/animegasan/luci-app-wolplus.git package/luci-app-wolplus
git clone --depth 1 https://github.com/sbwml/luci-app-mosdns -b v5 package/mosdns
git clone --depth 1 https://github.com/sbwml/v2ray-geodata package/v2ray-geodata
git clone --depth 1 https://github.com/vernesong/OpenClash.git package/openclash
git clone --depth 1 https://github.com/sirpdboy/luci-app-ddns-go.git package/ddns-go
git clone --depth 1 https://github.com/immortalwrt/homeproxy.git package/homeproxy
git clone --depth 1 https://github.com/m0eak/openwrt_patch.git ./package/custom
git clone -b js --depth 1 https://github.com/papagaye744/luci-theme-design.git package/luci-theme-design
git clone --depth 1 https://github.com/xuanranran/luci-app-design-config.git package/luci-app-design-config




