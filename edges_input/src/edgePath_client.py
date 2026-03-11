import grpc
import sys

import getPath_service_pb2
import getPath_service_pb2_grpc

def user_loop(address: str):
    with grpc.insecure_channel(address) as channel:
        stub = getPath_service_pb2_grpc.PathServiceStub(channel)

        user_input = ""
        while user_input != "finish":

            while user_input != "start" and user_input != "finish":
                user_input = input("\nEnter a command (start/finish) : ")

            numOfEdges = 0
            if user_input == "start":
                try:
                    response = stub.StartEnv(getPath_service_pb2.Empty())
                    numOfEdges = response.numOfEdges

                    print("\n" + response.message)

                    if numOfEdges == 0: user_input = "finish"

                except Exception as e:
                    print(f"Server Error : {e}")
                    return

            while user_input != "end" and user_input != "finish":

                user_input = ""
                while user_input != "ask" and user_input != "end":
                    user_input = input("\nEnter a command (ask/end) : ")

                if user_input == "ask":
                    user_input = input(f"Enter the starting edge, target edge (between 0 and {numOfEdges - 1})\nand optionnaly the timestep (between 0 and 300) : ")

                    start, target, timestep = map(int, user_input.split())

                    try:
                        request = getPath_service_pb2.InitialData(start_edge=start, target_edge=target, timestep=timestep)
                        response = stub.GetPathToTarget(request)

                        edges = ""
                        for i in range(len(response.edges)):
                            edges += str(response.edges[i])
                            if i != len(response.edges) - 1:
                                edges += " - "
                        print(edges)
                    
                    except Exception as e:
                        print(f"Server Error : {e}")
                        return

                if user_input == "end":
                    try:
                        response = stub.EndEnv(getPath_service_pb2.Empty())
                        numOfEdges = 0

                        print("\n" + response.message)
                    except Exception as e:
                        print(f"Server Error : {e}")
                        return

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_loop(sys.argv[1])
    else:
        print("Please provide the IP Address")