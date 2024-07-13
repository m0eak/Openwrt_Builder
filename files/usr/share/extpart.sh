#!/bin/sh

# 列出现有分区
echo "现有的分区如下："
blkid /dev/mmcblk0* || blkid /dev/sd*

# 提示用户选择分区，并设置默认值
echo "请选择要使用的分区（例如/dev/mmcblk0p1，默认值为 /dev/mmcblk0p1）："
read partition

# 如果用户未输入，使用默认值
if [ -z "$partition" ]; then
    partition="/dev/mmcblk0p1"
fi

# 提示用户确认格式化分区
echo "你选择的分区是 $partition。格式化该分区将会删除所有数据。请确保整个u盘或tf卡上没有重要文件。"
echo "你确定要继续吗？(y/n)"
read confirmation

if [ "$confirmation" != "y" ]; then
    echo "操作已取消。"
    exit 1
fi

# 取消挂载分区
umount $partition

# 格式化分区为 ext4 文件系统
mkfs.ext4 -F $partition

# 挂载分区
mount -t ext4 $partition /mnt

# 创建临时目录并绑定当前根目录
mkdir /tmp/root
mount -o bind / /tmp/root

# 复制所有文件到新分区
cp /tmp/root/* /mnt -a

# 等待2秒
sleep 2s

# 取消挂载临时目录和新分区
umount /tmp/root
umount /mnt

# 更新 fstab 配置文件
block detect > /etc/config/fstab
uci set fstab.@mount[0].target='/overlay'
uci set fstab.@mount[0].enabled='1'
uci commit fstab

# 重启系统
reboot
