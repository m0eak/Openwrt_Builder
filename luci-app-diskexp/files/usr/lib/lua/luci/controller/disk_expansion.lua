module("luci.controller.disk_expansion", package.seeall)

function index()
    entry({"admin", "system", "disk_expansion"}, cbi("disk_expansion"), _("Disk Expansion"), 60).dependent = true
end