import grpc
import sys
from google.protobuf import empty_pb2

import coSim_pb2
import coSim_pb2_grpc


# RPCs available on the CoSim service (matches coSim.proto)
RPC_COMMANDS = ["Start", "GetAttribute", "Finish", "exit"]


def call_start(stub):
    """Calls Start(Config) → google.protobuf.Empty"""
    config = coSim_pb2.Config(path="")

    print("\n📤 Sending Start(Config):")
    print(f"  Config.path: '{config.path}'")

    stub.Start(config)

    print("\n📥 Received Empty response")
    print("✓ Start RPC completed")


def call_get_attribute(stub):
    """Calls GetAttribute(Request) → Request"""
    user_input = input("Enter starting edge ID and destination edge ID: ")
    start_edge, dest_edge = map(int, user_input.split())

    ts_input = input("Enter timestamp (optional, press Enter for 0.0): ").strip()
    timestamp = float(ts_input) if ts_input else 0.0

    request = coSim_pb2.Request(
        attribute=coSim_pb2.Request.Attribute.ROUTE,
        forAll=False,
        type=coSim_pb2.Request.RequestType.GET,
        category=coSim_pb2.Request.Category.ROAD,
        id="vehicle_1",
        value=coSim_pb2.ValueType(
            stringArray=coSim_pb2.ValueType.StringArray(
                values=[str(start_edge), str(dest_edge)]
            )
        ),
        requestId=f"req_{start_edge}_{dest_edge}",
        timestamp=timestamp,
        entity_type=coSim_pb2.EntityType.CAR
    )

    print("\n📤 Sending GetAttribute(Request):")
    print(f"  attribute:    ROUTE ({request.attribute})")
    print(f"  forAll:       {request.forAll}")
    print(f"  type:         GET ({request.type})")
    print(f"  category:     ROAD ({request.category})")
    print(f"  id:           '{request.id}'")
    print(f"  value:        StringArray({list(request.value.stringArray.values)})")
    print(f"  requestId:    '{request.requestId}'")
    print(f"  timestamp:    {request.timestamp}")
    print(f"  entity_type:  CAR ({request.entity_type})")

    response = stub.GetAttribute(request)

    edges = list(response.value.stringArray.values)
    print("\n📥 Received GetAttribute response (Request):")
    print(f"  attribute:    ROUTE ({response.attribute})")
    print(f"  type:         GET ({response.type})")
    print(f"  category:     ROAD ({response.category})")
    print(f"  id:           '{response.id}'")
    print(f"  value:        StringArray({edges})")
    print(f"  requestId:    '{response.requestId}'")

    print(f"\n✓ Route from edge {start_edge} to edge {dest_edge}:")
    print(f"  {' → '.join(edges)}")
    print(f"  Total edges: {len(edges)}")


def call_finish(stub):
    """Calls Finish(Empty) → Empty"""
    finish_request = empty_pb2.Empty()

    print("\n📤 Sending Finish(Empty)")

    stub.Finish(finish_request)

    print("\n📥 Received Empty response")
    print("✓ Finish RPC completed")


def user_loop(address: str):
    with grpc.insecure_channel(address) as channel:
        stub = coSim_pb2_grpc.CoSimStub(channel)

        print(f"Connected to CoSim server at {address}")
        print(f"Available RPCs: {', '.join(RPC_COMMANDS)}")

        while True:
            command = input(f"\nEnter RPC to call ({'/'.join(RPC_COMMANDS)}): ").strip()

            if command == "exit":
                print("Exiting client")
                break

            if command not in RPC_COMMANDS:
                print(f"Unknown command. Available: {', '.join(RPC_COMMANDS)}")
                continue

            try:
                if command == "Start":
                    call_start(stub)
                elif command == "GetAttribute":
                    call_get_attribute(stub)
                elif command == "Finish":
                    call_finish(stub)

            except ValueError:
                print("Error: Please enter two space-separated integers")
            except grpc.RpcError as e:
                print(f"gRPC Error: {e.code().name} — {e.details()}")
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else "localhost:50051"
    user_loop(address)
