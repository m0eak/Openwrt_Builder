local fs = require "nixio.fs"
local sys = require "luci.sys"
local util = require "luci.util"

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
    
    -- Add revert option
    local revert = f:field(Button, "_revert", translate("Revert Expansion"))
    revert.inputtitle = translate("Revert Expansion")
    revert.inputstyle = "remove"
    revert.description = translate("WARNING: Reverting the expansion will cause you to lose all current settings and configurations!")
    
    function revert.write(self, section)
        luci.sys.call("rm -f /etc/config/fstab && touch /etc/disk_expansion_reverted && reboot &")
        luci.http.redirect(luci.dispatcher.build_url("admin", "system", "disk_expansion") .. "?reverted=1")
    end

    f.submit = false
    f.reset = false
end

-- Include JavaScript for better UX
f.description = f.description .. [[
<script type="text/javascript">
document.addEventListener('DOMContentLoaded', function() {
    // Success/status messages
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('expanded')) {
        alert(']] .. translate("Disk expansion initiated. The system will restart soon to complete the process.") .. [[');
    }
    if (urlParams.has('reverted')) {
        alert(']] .. translate("Expansion has been reverted. The system will restart now.") .. [[');
    }
    
    // Confirmation for expansion
    var expandBtn = document.querySelector('input[type="submit"]');
    if (expandBtn) {
        expandBtn.addEventListener('click', function(e) {
            var select = document.querySelector('select[name="partition"]');
            if (select && select.value) {
                if (!confirm(']] .. translate("WARNING: This will format the selected partition") .. [[ (' + select.value + ') ]] .. translate("and ALL DATA on it will be LOST.") .. [[\n\n]] .. translate("Are you sure you want to continue?") .. [[')) {
                    e.preventDefault();
                    return false;
                }
            }
        });
    }
    
    // Confirmation for reverting
    var revertBtn = document.querySelector('input[name="_revert"]');
    if (revertBtn) {
        revertBtn.addEventListener('click', function(e) {
            if (!confirm(']] .. translate("WARNING: Reverting the expansion will DELETE all current settings and configurations.") .. [[\n\n]] .. translate("The system will return to its factory state. Are you sure you want to continue?") .. [[')) {
                e.preventDefault();
                return false;
            }
        });
    }
    
    // Apply some styling
    document.querySelectorAll('.cbi-section').forEach(function(section) {
        section.style.background = '#f9f9f9';
        section.style.borderRadius = '5px';
        section.style.padding = '15px';
        section.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
    });
});
</script>
]]

return f