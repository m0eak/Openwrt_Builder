#
# Copyright (C) 2023 Your Name <your.email@example.com>
#
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-disk-expansion
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

PKG_LICENSE:=GPL-3.0-or-later
PKG_MAINTAINER:=m0eak <moeakyou@gmail.com>

LUCI_TITLE:=Disk Expansion
LUCI_DESCRIPTION:=LuCI application for expanding root filesystem to external storage.
LUCI_DEPENDS:=+block-mount +e2fsprogs +kmod-usb-storage +kmod-fs-ext4 +kmod-fs-vfat
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

define Package/$(PKG_NAME)/install
	# 安装LuCI控制器（注意：以下每行命令前必须是TAB缩进）
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/controller
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/controller/disk_expansion.lua $(1)/usr/lib/lua/luci/controller/
	
	# 安装CBI模型
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/model/cbi/disk_expansion.lua $(1)/usr/lib/lua/luci/model/cbi/
	
	# 安装执行脚本
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/disk_expansion.sh $(1)/usr/bin/
	
	# 安装UCI默认配置
	$(INSTALL_DIR) $(1)/etc/uci-defaults
	$(INSTALL_BIN) ./files/etc/uci-defaults/40_luci-disk-expansion $(1)/etc/uci-defaults/
endef

# 必须放在文件最后
$(eval $(call BuildPackage,$(PKG_NAME)))
