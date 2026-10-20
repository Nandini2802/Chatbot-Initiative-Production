
import asyncio

from redis.asyncio import Redis
from redis_entraid.cred_provider import (
    create_from_default_azure_credential,
)


async def main():

    print("\n========== REDIS CLUSTER DIAGNOSTIC ==========")

    credential_provider = create_from_default_azure_credential(
        ("https://redis.azure.com/.default",)
    )

    client = Redis(
        host="redis-danubeone-prod-weu.francecentral.redis.azure.net",
        port=10000,
        ssl=True,
        ssl_cert_reqs="required",
        credential_provider=credential_provider,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )

    try:
        print("[1] Checking Redis connection...")

        ping_result = await client.ping()

        print(f"[SUCCESS] Redis PING: {ping_result}")

        print("\n[2] Fetching Redis Cluster nodes...")

        nodes = await client.execute_command(
            "CLUSTER", "SLOTS"
        )

        print("\n========== CLUSTER SLOTS ==========")

        for node_range in nodes:

            print(
                f"\nSlot range: {node_range[0]} - {node_range[1]}"
            )

            for node in node_range[2:]:
                print(
                    f"Node address: {node[0]} | Port: {node[1]}"
                )

        print("\n[3] Cluster diagnostic completed.")

    except Exception as exc:
        import traceback

        print(
            f"\n[ERROR] {type(exc).__name__}: {exc}"
        )

        traceback.print_exc()

    finally:
        await client.aclose()

        print("\nRedis connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
