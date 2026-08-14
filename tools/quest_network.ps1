function Get-OrenQuestNetwork {
    [CmdletBinding()]
    param()

    $virtualPattern = 'Loopback|vEthernet|Docker|WSL|Hyper-V|VirtualBox|VMware|Tailscale'
    $candidates = foreach ($config in Get-NetIPConfiguration -ErrorAction SilentlyContinue) {
        if (-not $config.NetAdapter -or $config.NetAdapter.Status -ne 'Up' -or -not $config.IPv4DefaultGateway) { continue }
        if ($config.InterfaceAlias -match $virtualPattern) { continue }
        foreach ($address in $config.IPv4Address) {
            if (-not $address.IPAddress -or $address.IPAddress -like '127.*' -or $address.IPAddress -like '169.254.*') { continue }
            $profile = Get-NetConnectionProfile -InterfaceIndex $config.InterfaceIndex -ErrorAction SilentlyContinue | Select-Object -First 1
            [pscustomobject]@{
                IPAddress = $address.IPAddress
                InterfaceAlias = $config.InterfaceAlias
                InterfaceIndex = $config.InterfaceIndex
                InterfaceMetric = [int]$config.NetAdapter.InterfaceMetric
                NetworkName = if ($profile) { $profile.Name } else { $config.InterfaceAlias }
                NetworkCategory = if ($profile) { [string]$profile.NetworkCategory } else { 'Unknown' }
                Gateway = $config.IPv4DefaultGateway.NextHop
            }
        }
    }
    $selected = $candidates | Sort-Object InterfaceMetric, InterfaceIndex | Select-Object -First 1
    if (-not $selected) {
        throw 'Nao foi encontrada uma interface LAN ativa com IPv4 e gateway padrao.'
    }
    return $selected
}
