# RazaAI Test Network Standard

The fictional RazaAI laboratory network uses VLAN 731 for its management network.
The management gateway is 10.73.1.1.

DNS troubleshooting procedure:
1. Verify client IP address and subnet mask.
2. Verify the default gateway.
3. Test gateway reachability.
4. Test reachability to an external IP.
5. Test DNS resolution separately.
6. Inspect configured DNS servers before changing configuration.

Do not recommend changing DNS merely because Internet access is unavailable. Connectivity and name resolution must be tested independently.
