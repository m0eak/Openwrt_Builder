include $(TOPDIR)/rules.mk

PKG_NAME:=m0eak-default-settings
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPLv3
PKG_LICENSE_FILES:=LICENSE

include $(INCLUDE_DIR)/package.mk

define Package/m0eak-default-settings
  SECTION:=luci
  CATEGORY:=LuCI
  TITLE:=LuCI support for Default Settings
  PKGARCH:=all
  DEPENDS:=+luci-base +luci

define Package/default-settings/description
  LuCI support for Default Settings.
endef

# This is a pure config package, no compilation needed
define Build/Compile
endef

define Package/default-settings/install
        $(INSTALL_DIR) $(1)/etc/uci-defaults
        $(INSTALL_BIN) ./files/zzz_m0eak $(1)/etc/uci-defaults/zzz_m0eak
endef

$(eval $(call BuildPackage,default-settings))