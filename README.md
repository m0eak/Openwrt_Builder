# OpenWrt Builder

这是一个基于 GitHub Actions 的 OpenWrt/ImmortalWrt 固件构建仓库，主要用于按设备配置自动拉取源码、注入自定义包、应用默认设置并产出固件。

## 支持设备

- GL.iNet AXT-1800，默认 IP：`192.168.8.1`
- JDC-AX6600，默认 IP：`192.168.100.1`
- GL-MT5000，默认 IP：`192.168.100.1`
- GL-MT3600BE，默认 IP：`192.168.9.1`
- Tenda BE12 Pro
- TR-3000，默认 IP：`192.168.6.1`
- x86 ImmortalWrt，默认 IP：`192.168.100.1`

## 目录结构

- `.github/workflows/`：GitHub Actions 构建与测试入口。
- `config/`：各设备的 OpenWrt `.config` 配置片段。
- `sh/scripts-part1.sh`：feeds 更新前执行的设备特定源码修改。
- `sh/scripts-part2.sh`：feeds 安装后执行的自定义包注入与冲突包清理。
- `default-settings-m0eak/`：自定义默认设置包。
- `files/`：OpenWrt rootfs overlay，会被复制到构建树的 `openwrt/files`。

## 构建流程

1. GitHub Actions 根据 workflow matrix 选择设备和配置文件。
2. 克隆对应 OpenWrt/ImmortalWrt 源码。
3. 执行 `sh/scripts-part1.sh`，处理源码级补丁、默认 IP、vermagic 等前置修改。
4. 更新并安装 feeds。
5. 注入 `default-settings-m0eak`、`files/` 和设备 `.config`。
6. 执行 `sh/scripts-part2.sh`，清理冲突 Makefile 并克隆第三方自定义包。
7. `make defconfig`、下载依赖、编译固件并上传产物。

## AdGuardHome 说明

`files/etc/AdGuardHome.yaml` 中保留过滤规则订阅 URL。规则缓存目录 `files/etc/AdGuardHome/data/filters/` 不再提交到仓库，避免把过期的运行时缓存打进固件，也减少仓库体积。

## 本地检查

在有 Bash 的环境中，可以先做脚本语法检查：

```bash
bash -n sh/scripts-part1.sh
bash -n sh/scripts-part2.sh
```

完整固件构建建议在 GitHub Actions 中验证。

## 致谢

- [P3TERX/Actions-OpenWrt](https://github.com/P3TERX/Actions-OpenWrt)
- [OpenWrt](https://github.com/openwrt/openwrt)
- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)

## License

[MIT](LICENSE)
