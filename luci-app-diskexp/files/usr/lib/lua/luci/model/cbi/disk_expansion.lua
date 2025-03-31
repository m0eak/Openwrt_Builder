local fs = require "nixio.fs"
local sys = require "luci.sys"
local util = require "luci.util"
local http = require "luci.http"

-- Check if already expanded
local function is_expanded()
    local fstab = io.open("/etc/config/fstab", "r")
    if fstab then
        local content = fstab:read("*all")
        fstab:close()
        return content:match("option%s+target%s+['\"]?/overlay['\"]?") ~= nil
    end
    return false
end

-- Get available partitions
local function get_partitions()
    local partitions = {}
    
    -- Try mmcblk devices
    local blkid_mmcblk = util.exec("blkid /dev/mmcblk0* 2>/dev/null")
    if blkid_mmcblk and #blkid_mmcblk > 0 then
        for dev in blkid_mmcblk:gmatch("/dev/mmcblk0[^:]+") do
            partitions[#partitions+1] = dev
        end
    end
    
    -- Try sd devices
    local blkid_sd = util.exec("blkid /dev/sd* 2>/dev/null")
    if blkid_sd and #blkid_sd > 0 then
        for dev in blkid_sd:gmatch("/dev/sd[^:]+") do
            partitions[#partitions+1] = dev
        end
    end
    
    return partitions
end

-- Create form instead of map
f = SimpleForm("disk_expansion", translate("Disk Expansion"), translate("Expand your root filesystem to external storage"))

-- Only show expansion options if not already expanded
if not is_expanded() then
    -- Create partition selection dropdown
    part = f:field(ListValue, "partition", translate("Select Partition"))
    part.description = translate("Choose a partition to expand your root filesystem to. WARNING: This operation will format the selected partition and ALL DATA on it will be LOST.")
    
    -- Add partition options
    local partitions = get_partitions()
    if #partitions > 0 then
        for _, v in ipairs(partitions) do
            part:value(v, v)
        end
    else
        part:value("", translate("No suitable partitions found"))
    end
    
    -- Add expansion button
    f.submit = translate("Expand Now")
    f.reset = false
    
    function f.handle(self, state, data)
        if state == FORM_VALID then
            local partition = data.partition
            if partition and #partition > 0 then
                luci.sys.call("sh /usr/bin/disk_expansion.sh " .. partition .. " > /tmp/disk_expansion.log 2>&1 &")
                luci.http.redirect(luci.dispatcher.build_url("admin", "system", "disk_expansion") .. "?expanded=1")
            end
            return true
        end
        return true
    end
else
    -- Show expanded status message
    local msg = f:field(DummyValue, "_note", translate("Status"))
    msg.rawhtml = true
    msg.value = '<span style="color:green;font-weight:bold;">' .. translate("The root filesystem has been expanded.") .. '</span>'
    
    -- 使用纯HTML链接作为撤销按钮
    local revert = f:field(DummyValue, "_revert_link", translate("Revert Expansion"))
    revert.rawhtml = true
    revert.value = string.format(
        '<a href="%s" class="btn cbi-button cbi-button-remove" style="color:#fff;background-color:#dc3545;border-color:#dc3545;padding:5px 10px;border-radius:4px;text-decoration:none;" onclick="return confirm(\'%s\')">%s</a>' ..
        '<p><span style="color:red;display:block;margin-top:5px;">%s</span></p>',
        luci.dispatcher.build_url("admin", "system", "disk_expansion", "revert"),
        util.pcdata(translate("WARNING: Reverting the expansion will DELETE all current settings and configurations. The system will return to its factory state. Are you sure you want to continue?")),
        translate("Revert Expansion"),
        translate("WARNING: Reverting the expansion will cause you to lose all current settings and configurations!")
    )

    f.submit = false
    f.reset = false
end

-- 添加简单JavaScript进行URL参数检查
local js = [[
<script type="text/javascript">
document.addEventListener('DOMContentLoaded', function() {
    // Success/status messages
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('expanded')) {
        alert('%s');
    }
    if (urlParams.has('reverted')) {
        alert('%s');
    }
}); 

// 为扩展按钮添加确认
document.addEventListener('DOMContentLoaded', function() {
    var expandButton = document.querySelector('input[type="submit"][name="cbi.submit"]');
    if (expandButton) {
        expandButton.addEventListener('click', function(e) {
            var select = document.querySelector('select[name="partition"]');
            if (select && select.value) {
                if (!confirm('%s ' + select.value + ' %s')) {
                    e.preventDefault();
                    return false;
                }
            }
        });
    }
});
</script>
]]

-- 安全地添加JavaScript
f.description = f.description .. string.format(js,
    util.pcdata(translate("Disk expansion initiated. The system will restart soon to complete the process.")),
    util.pcdata(translate("Expansion has been reverted. The system will restart now.")),
    util.pcdata(translate("WARNING: This will format the selected partition")),
    util.pcdata(translate("and ALL DATA on it will be LOST. Are you sure you want to continue?"))
)

return f
