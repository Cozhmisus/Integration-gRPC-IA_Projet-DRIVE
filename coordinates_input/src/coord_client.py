import grpc
import sys

import coord_service_pb2
import coord_service_pb2_grpc

def user_loop(address: str):
    with grpc.insecure_channel(address) as channel:
        stub = coord_service_pb2_grpc.PathServiceStub(channel)

        user_input = ""
        while user_input != "finish":
            
            while user_input != "start" and user_input != "finish":
                user_input = input("\nEnter a command (start/finish) : ").lower()

            if user_input == "start":
                try:
                    response = stub.StartEnv(coord_service_pb2.Empty())
                    max_coord = response.max_coord

                    print("\n" + response.message)

                    if len(max_coord) != 2: user_input = "finish"

                except Exception as e:
                    print(f"Server Error : {e}")
                    return

            while user_input != "end" and user_input != "finish":

                user_input = ""
                while user_input != "ask" and user_input != "end":
                    user_input = input("\nEnter a command (ask/end) : ").lower()

                if user_input == "ask":
                    start = [0] * 2
                    target = [0] * 2

                    user_input = input(f"Enter the starting coord (x : 0 to {max_coord[0]} / y : 0 to {max_coord[1]}) : ")
                    start = map(int, user_input.split())

                    user_input = input(f"Enter the target coord (x : 0 to {max_coord[0]} / y : 0 to {max_coord[1]}) : ")
                    target = map(int, user_input.split())

                    user_input = input(f"Enter the timestep (0 to 300) : ")
                    timestep = int(user_input)

                    try:
                        request = coord_service_pb2.InitialData(start_coord=start, target_coord=target, timestep=timestep)
                        response = stub.GetPathToTarget(request)

                        if len(response.edges) > 0:
                            print(f"\n{response.message}{response.start_type} {response.start_index} - {response.target_type} {response.target_index}")

                            edges = ""
                            for i in range(len(response.edges)):
                                edges += str(response.edges[i])
                                if i != len(response.edges) - 1:
                                    edges += " - "
                            print(edges)

                        else:
                            print(response.message)
                    
                    except Exception as e:
                        print(f"Server Error : {e}")
                        return

                if user_input == "end":
                    try:
                        response = stub.EndEnv(coord_service_pb2.Empty())

                        print("\n" + response.message)
                    except Exception as e:
                        print(f"Server Error : {e}")
                        return

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_loop(sys.argv[1])
    else:
        print("Please provide the IP Address")