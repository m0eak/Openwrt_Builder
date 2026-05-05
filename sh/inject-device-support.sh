#!/bin/bash

# ============================================================
# 脚本功能：从 ImmortalWrt 注入 jdcloud_re-ss-01 设备支持
# 使用方法：在 fanchmwrt 源码目录中执行此脚本
# ============================================================

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  注入 jdcloud_re-ss-01 设备支持${NC}"
echo -e "${GREEN}=============================================${NC}"

# 源码目录（当前目录）
OPENWRT_DIR="$PWD"

# ImmortalWrt 源码地址
IMMORTALWRT_URL="https://github.com/immortalwrt/immortalwrt.git"
IMMORTALWRT_BRANCH="master"

# 临时目录
TEMP_DIR="/tmp/immortalwrt-device-inject"

# 清理临时目录
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo -e "${YELLOW}[1/4] 克隆 ImmortalWrt 源码（仅 target/linux/qualcommax）...${NC}"

# 浅克隆 ImmortalWrt，只获取 qualcommax 相关代码
cd "$TEMP_DIR"
git clone -b "$IMMORTALWRT_BRANCH" "$IMMORTALWRT_URL" --single-branch --depth 1 --filter=blob:none immortalwrt-temp 2>/dev/null || \
git clone -b "$IMMORTALWRT_BRANCH" "$IMMORTALWRT_URL" --single-branch --depth 1 immortalwrt-temp

cd immortalwrt-temp

# 确保获取 target/linux/qualcommax 目录
git sparse-checkout set target/linux/qualcommax 2>/dev/null || true
git checkout 2>/dev/null || true

echo -e "${YELLOW}[2/4] 复制 qualcommax/ipq60xx 设备支持文件...${NC}"

# 目标目录
TARGET_DIR="$OPENWRT_DIR/target/linux/qualcommax"

# 如果目标目录不存在则创建
mkdir -p "$TARGET_DIR"

# 复制 ipq60xx 目录（如果 fanchmwrt 中已存在则合并）
if [ -d "target/linux/qualcommax/ipq60xx" ]; then
    cp -rf target/linux/qualcommax/ipq60xx/* "$TARGET_DIR/ipq60xx/" 2>/dev/null || \
    cp -rf target/linux/qualcommax/ipq60xx "$TARGET_DIR/"
    echo -e "${GREEN}  ✅ 已复制 target/linux/qualcommax/ipq60xx 目录${NC}"
fi

# 复制 dts 目录
if [ -d "target/linux/qualcommax/dts" ]; then
    cp -rf target/linux/qualcommax/dts/* "$TARGET_DIR/dts/" 2>/dev/null || \
    cp -rf target/linux/qualcommax/dts "$TARGET_DIR/"
    echo -e "${GREEN}  ✅ 已复制 target/linux/qualcommax/dts 目录${NC}"
fi

# 复制 image 目录
if [ -d "target/linux/qualcommax/image" ]; then
    cp -rf target/linux/qualcommax/image/* "$TARGET_DIR/image/" 2>/dev/null || \
    cp -rf target/linux/qualcommax/image "$TARGET_DIR/"
    echo -e "${GREEN}  ✅ 已复制 target/linux/qualcommax/image 目录${NC}"
fi

echo -e "${YELLOW}[3/4] 检查并修复设备配置...${NC}"

# 确保 ipq60xx.mk 中包含 jdcloud_re-ss-01 设备定义
if [ -f "$TARGET_DIR/image/ipq60xx.mk" ]; then
    if grep -q "jdcloud_re-ss-01" "$TARGET_DIR/image/ipq60xx.mk"; then
        echo -e "${GREEN}  ✅ jdcloud_re-ss-01 设备定义已存在${NC}"
    else
        echo -e "${RED}  ❌ 未找到 jdcloud_re-ss-01 设备定义，尝试手动添加...${NC}"
        
        # 添加设备定义到 ipq60xx.mk
        cat >> "$TARGET_DIR/image/ipq60xx.mk" << 'EOF'

define Device/jdcloud_re-ss-01
	$(call Device/FitImage)
	DEVICE_VENDOR := JDCloud
	DEVICE_MODEL := RE-SS-01
	SOC := ipq6000
	BLOCKSIZE := 64k
	KERNEL_SIZE := 6144k
	DEVICE_DTS_CONFIG := config@cp03-c2
	DEVICE_PACKAGES := ipq-wifi-jdcloud_re-ss-01
endef
TARGET_DEVICES += jdcloud_re-ss-01
EOF
        echo -e "${GREEN}  ✅ 已添加 jdcloud_re-ss-01 设备定义${NC}"
    fi
else
    echo -e "${RED}  ❌ 未找到 ipq60xx.mk 文件${NC}"
fi

# 确保 ipq60xx 目录有 target.mk 文件
if [ ! -f "$TARGET_DIR/ipq60xx/target.mk" ]; then
    mkdir -p "$TARGET_DIR/ipq60xx"
    cat > "$TARGET_DIR/ipq60xx/target.mk" << 'EOF'
SUBTARGET:=ipq60xx
BOARDNAME:=Qualcomm Atheros IPQ60xx
DEFAULT_PACKAGES += ath11k-firmware-ipq6018
define Target/Description
	Build firmware images for Qualcomm Atheros IPQ60xx based boards.
endef
EOF
    echo -e "${GREEN}  ✅ 已创建 ipq60xx/target.mk${NC}"
fi

# 确保 ipq60xx 目录有 config-default 文件
if [ ! -f "$TARGET_DIR/ipq60xx/config-default" ]; then
    mkdir -p "$TARGET_DIR/ipq60xx"
    cat > "$TARGET_DIR/ipq60xx/config-default" << 'EOF'
CONFIG_IPQ_CMN_PLL=y
CONFIG_IPQ_GCC_6018=y
CONFIG_MTD_SPLIT_FIT_FW=y
CONFIG_PINCTRL_IPQ6018=y
CONFIG_PWM=y
CONFIG_PWM_IPQ=y
CONFIG_QCOM_APM=y
# CONFIG_QCOM_CLK_SMD_RPM is not set
# CONFIG_QCOM_RPMPD is not set
CONFIG_QCOM_SMD_RPM=y
CONFIG_REGULATOR_CPR3=y
# CONFIG_REGULATOR_CPR3_NPU is not set
CONFIG_REGULATOR_CPR4_APSS=y
CONFIG_REGULATOR_QCOM_SMD_RPM=y
EOF
    echo -e "${GREEN}  ✅ 已创建 ipq60xx/config-default${NC}"
fi

echo -e "${YELLOW}[4/4] 检查 qualcommax/Makefile...${NC}"

# 确保 qualcommax/Makefile 中包含 ipq60xx 子目标
if [ -f "$TARGET_DIR/Makefile" ]; then
    if grep -q "ipq60xx" "$TARGET_DIR/Makefile"; then
        echo -e "${GREEN}  ✅ qualcommax/Makefile 已包含 ipq60xx 子目标${NC}"
    else
        echo -e "${YELLOW}  ⚠️  qualcommax/Makefile 中未找到 ipq60xx，可能需要手动添加${NC}"
    fi
else
    echo -e "${RED}  ❌ 未找到 qualcommax/Makefile 文件${NC}"
fi

# 清理临时目录
cd "$OPENWRT_DIR"
rm -rf "$TEMP_DIR"

echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  ✅ jdcloud_re-ss-01 设备支持注入完成！${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "现在可以使用以下配置进行编译："
echo -e "  CONFIG_TARGET_qualcommax=y"
echo -e "  CONFIG_TARGET_qualcommax_ipq60xx=y"
echo -e "  CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_jdcloud_re-ss-01=y"
echo ""
