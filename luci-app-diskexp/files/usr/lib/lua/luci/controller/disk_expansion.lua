module("luci.controller.disk_expansion", package.seeall)

function index()
    entry({"admin", "system", "disk_expansion"}, cbi("disk_expansion"), _("Disk Expansion"), 60).dependent = true
    entry({"admin", "system", "disk_expansion", "revert"}, call("action_revert"))
end

function action_revert()
    -- 记录日志
    local log = io.open("/tmp/disk_revert.log", "w")
    if log then
        log:write("Revert action triggered at " .. os.date())
        log:close()
    end
    
    -- 执行撤销命令
    luci.sys.call("rm -f /etc/config/fstab")
    luci.sys.call("touch /etc/disk_expansion_reverted")
    
    -- 等待配置改变
    luci.sys.call("sync")
    
    -- 设置重启标志
    luci.sys.call("(sleep 3 && reboot) &")
    
    -- 重定向到成功页面
    luci.http.redirect(luci.dispatcher.build_url("admin", "system", "disk_expansion") .. "?reverted=1")
end
