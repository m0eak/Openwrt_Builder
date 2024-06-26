#!/bin/sh
umount /dev/mmcblk0p1
mkfs.ext4 -F /dev/mmcblk0p1
mount -t ext4 /dev/mmcblk0p1 /mnt
mkdir /tmp/root
mount -o bind / /tmp/root
cp /tmp/root/* /mnt -a
sleep 2s
umount /tmp/root
umount /mnt
block detect > /etc/config/fstab
uci set fstab.@mount[0].target='/overlay'
uci set fstab.@mount[0].enabled='1'root
uci commit fstab
reboot
