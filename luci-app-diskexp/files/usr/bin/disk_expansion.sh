#!/bin/sh

# Check if partition parameter is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <partition>"
    exit 1
fi

# Get partition parameter
partition="$1"

# Check dependencies
if [ -x "$(command -v opkg)" ]; then
    PACKAGE_MANAGER="opkg list-installed"
    echo "Using opkg package manager."
elif [ -x "$(command -v apk)" ]; then
    PACKAGE_MANAGER="apk list --installed"
    echo "Using apk package manager."
else
    echo "No valid package manager found."
    exit 1
fi

if [ "$( $PACKAGE_MANAGER 2>/dev/null| grep -c "block-mount")" -ne '0' ] && [ "$( $PACKAGE_MANAGER 2>/dev/null| grep -c "e2fsprogs")" -ne '0' ] && [ "$( $PACKAGE_MANAGER 2>/dev/null| grep -c "kmod-usb-storage")" -ne '0' ] && [ "$( $PACKAGE_MANAGER 2>/dev/null| grep -c "kmod-fs-vfat")" -ne '0' ];then
  echo "Dependencies check passed"
else
  echo "Missing dependencies, please install: block-mount kmod-usb-storage kmod-fs-ext4 e2fsprogs kmod-fs-vfat"
  exit 1
fi

# Unmount partition if mounted
umount $partition 2>/dev/null

# Format partition as ext4
mkfs.ext4 -F $partition

# Mount partition
mount -t ext4 $partition /mnt

# Create temporary directory and bind current root
mkdir -p /tmp/root
mount -o bind / /tmp/root

# Copy all files to new partition
cp -a /tmp/root/* /mnt/

# Wait 2 seconds
sleep 2s

# Unmount temporary directory and new partition
umount /tmp/root
umount /mnt

# Update fstab configuration file
block detect > /etc/config/fstab
uci set fstab.@mount[0].target='/overlay'
uci set fstab.@mount[0].enabled='1'
uci commit fstab

# Mark expansion as complete
touch /etc/disk_expanded

# Restart system
echo "Expansion completed. Restarting system..."
(sleep 3 && reboot) &

exit 0