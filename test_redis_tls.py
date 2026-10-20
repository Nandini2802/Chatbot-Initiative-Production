import socket
import ssl

HOST = "redis-danubeone-prod-weu.francecentral.redis.azure.net"
PORT = 8501

context = ssl.create_default_context()

try:
    print("[1] Connecting using Azure Redis hostname...")

    with socket.create_connection(
        (HOST, PORT),
        timeout=10,
    ) as sock:
        with context.wrap_socket(
            sock,
            server_hostname=HOST,
        ) as secure_sock:

            print("[SUCCESS] TLS handshake completed")
            print("[INFO] TLS version:", secure_sock.version())

except Exception as exc:
    print(
        "[ERROR]",
        type(exc).__name__,
        str(exc),
    )