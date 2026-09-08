import winrm


WINDOWS_CHECKS = {
    "system": (
        "Get-ComputerInfo | "
        "Select-Object CsName,WindowsProductName,"
        "WindowsVersion,OsBuildNumber"
    ),
    "addresses": (
        "Get-NetIPConfiguration | "
        "Select-Object InterfaceAlias,IPv4Address,"
        "IPv4DefaultGateway,DNSServer"
    ),
    "routes": (
        "Get-NetRoute -AddressFamily IPv4 | "
        "Sort-Object RouteMetric | "
        "Select-Object DestinationPrefix,"
        "NextHop,InterfaceAlias,RouteMetric"
    ),
    "dns": (
        "Get-DnsClientServerAddress -AddressFamily IPv4"
    ),
    "services_failed": (
        "Get-Service | "
        "Where-Object {$_.StartType -eq 'Automatic' "
        "-and $_.Status -ne 'Running'} | "
        "Select-Object Name,Status,StartType"
    ),
}


class WindowsReadOnlyAdapter:
    def __init__(self, target, password):
        self.target = target

        protocol = (
            "https"
            if target.get("https", True)
            else "http"
        )

        port = target.get(
            "port",
            5986 if protocol == "https" else 5985,
        )

        endpoint = (
            f"{protocol}://{target['host']}:{port}/wsman"
        )

        self.session = winrm.Session(
            endpoint,
            auth=(
                target["username"],
                password,
            ),
            transport=target.get(
                "transport",
                "ntlm",
            ),
            server_cert_validation=target.get(
                "server_cert_validation",
                "validate",
            ),
        )

    def run_check(self, check):
        if check not in WINDOWS_CHECKS:
            raise ValueError(
                f"Unsupported Windows read-only check: {check}"
            )

        result = self.session.run_ps(
            WINDOWS_CHECKS[check]
        )

        stdout = result.std_out.decode(
            "utf-8",
            errors="replace",
        )

        stderr = result.std_err.decode(
            "utf-8",
            errors="replace",
        )

        return {
            "success": result.status_code == 0,
            "exit_code": result.status_code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }

    @staticmethod
    def checks():
        return sorted(WINDOWS_CHECKS)
