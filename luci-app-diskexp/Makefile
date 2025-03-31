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
PKG_MAINTAINER:=Your Name <your.email@example.com>

LUCI_TITLE:=Disk Expansion
LUCI_DESCRIPTION:=LuCI application for expanding root filesystem to external storage.
LUCI_DEPENDS:=+block-mount +e2fsprogs +kmod-usb-storage +kmod-fs-ext4 +kmod-fs-vfat
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
