include $(TOPDIR)/rules.mk

PKG_NAME:=default-settings-m0eak
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPLv3
PKG_LICENSE_FILES:=LICENSE

include $(INCLUDE_DIR)/package.mk

define Package/default-settings-m0eak
  SECTION:=luci
  CATEGORY:=LuCI
  TITLE:=My Default Settings
  PKGARCH:=all
  DEPENDS:=+luci
endef

define Package/default-settings-m0eak/description
  My Default Settings.
endef

# This is a pure config package, no compilation needed
define Build/Compile
endef

define Package/default-settings-m0eak/install
  $(INSTALL_DIR) $(1)/etc/uci-defaults
  $(INSTALL_BIN) ./files/zzz_m0eak $(1)/etc/uci-defaults/
endef

$(eval $(call BuildPackage,default-settings-m0eak))