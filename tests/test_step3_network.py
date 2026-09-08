from app.tools.registry import ToolRegistry
from app.agent import RazaAgent

EXPECTED_TOOLS = {"get_system_info", "get_network_interfaces", "get_ip_configuration", "get_routing_table", "dns_lookup", "ping_host"}

def assert_success(result):
    if not result.success:
        raise AssertionError(f"{result.tool} failed: {result.error}")

def main():
    registry = ToolRegistry()
    print("\n========================================")
    print("RazaAI Step 3 Network Diagnostics Test")
    print("========================================\n")
    names = {tool["name"] for tool in registry.list_tools()}
    missing = EXPECTED_TOOLS - names
    if missing:
        raise AssertionError(f"Missing tools: {sorted(missing)}")
    print("[PASS] Registry contains all Step 3 tools")
    interfaces = registry.execute("get_network_interfaces")
    assert_success(interfaces)
    print(f"[PASS] get_network_interfaces ({interfaces.execution_time:.3f}s)")
    ip_config = registry.execute("get_ip_configuration")
    assert_success(ip_config)
    print(f"[PASS] get_ip_configuration ({ip_config.execution_time:.3f}s)")
    print(f"       Gateway: {ip_config.result.get('default_gateway')}")
    print(f"       DNS: {ip_config.result.get('dns_servers')}")
    routes = registry.execute("get_routing_table")
    assert_success(routes)
    print(f"[PASS] get_routing_table ({routes.execution_time:.3f}s)")
    dns = registry.execute("dns_lookup", {"hostname": "example.com"})
    assert_success(dns)
    if not dns.result["resolved"]:
        raise AssertionError(f"DNS did not resolve example.com: {dns.result}")
    print(f"[PASS] dns_lookup -> {dns.result['addresses']}")
    ping = registry.execute("ping_host", {"target": "127.0.0.1", "count": 2, "timeout": 1})
    assert_success(ping)
    if not ping.result["success"]:
        raise AssertionError(f"Loopback ping failed: {ping.result}")
    print("[PASS] ping_host -> 127.0.0.1")
    print("\nTesting RazaAI agent tool selection...\n")
    agent = RazaAgent()
    response = agent.ask(
        "Perform a read-only network health check on this computer. "
        "Inspect its IP configuration and routes, resolve example.com, "
        "and ping 127.0.0.1. Summarise what you find. "
        "Use the available live tools and do not invent results."
    )
    print("\n========================================")
    print("RazaAI RESPONSE")
    print("========================================\n")
    print(response)
    print("\n========================================")
    print("STEP 3 PASSED")
    print("========================================")

if __name__ == "__main__":
    main()
