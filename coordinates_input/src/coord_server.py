import grpc
import torch
import sys
from concurrent import futures
from pathlib import Path

import coord_service_pb2
import coord_service_pb2_grpc

from app import NetworkGraphEnvironment, DQNAgent, load_model, get_agent_path, get_nodes_distance

class GetPathServicer(coord_service_pb2_grpc.PathServiceServicer):
    def __init__(self):
        self.env = None
        self.agent = None

    def StartEnv(self, request, context):
        try:
            BASE_DIR = Path(__file__).resolve().parent.parent
            GRAPH_PATH = BASE_DIR / "models" / "final.h5"
            MODEL_PATH = BASE_DIR / "models" / "agent_final.pth"

            env = NetworkGraphEnvironment(GRAPH_PATH, reward_type="combined")
            
            base_agent_config = {
                'state_size': 2 + 2 + 1 + 3 + 1 + env.max_neighbors * 5,
                'action_size': env.max_neighbors,
                'hidden_size': 512,
                'learning_rate': 1e-4,
                'gamma': 0.99,
                'epsilon_start': 0.01,  # Low epsilon for testing
                'epsilon_end': 0.01,
                'epsilon_decay': 1.0,
                'memory_size': 20000,
                'batch_size': 128,
                'update_freq': 100,
                'device': 'cuda' if torch.cuda.is_available() else 'cpu'
            }

            final_model_agent = DQNAgent(**base_agent_config)

            agent = load_model(final_model_agent, MODEL_PATH)
        
            self.env = env
            self.agent = agent

            max_x = 0
            max_y = 0

            for node in env.node_coords:
                if node[0] > max_x:
                    max_x = node[0]
                
                if node[1] > max_y:
                    max_y = node[1]
            
            return coord_service_pb2.StartMessage(message="Success : Agent and Environement loaded successfully", max_coord=[max_x, max_y])
        
        except Exception as e:
            
            return coord_service_pb2.StartMessage(message=f"Error : {e}" , max_coord=[])
        
    def EndEnv(self, request, context):
        self.env = None
        self.agent = None

        return coord_service_pb2.EndMessage(message="Agent and Environement unloaded")
    
    def GetClosestNodeFromEdgeToEdge(self, start_edge, target_edge):
        
        start_nodes = [self.env.edge_indices[start_edge][0], self.env.edge_indices[start_edge][1]]
        target_nodes = [self.env.edge_indices[target_edge][0], self.env.edge_indices[target_edge][1]]

        returned_start = 0
        returned_target = 0
        min_distance = sys.maxsize

        for start_node in start_nodes:
            for target_node in target_nodes:
                dist = get_nodes_distance(self.env.G.nodes[start_node]["pos"], self.env.G.nodes[target_node]["pos"])
                if dist < min_distance:
                    returned_start = start_node
                    returned_target = target_node
                    min_distance = dist

        return returned_start, returned_target

    def GetClosestEntity(self, coord):
        px = coord[0]
        py = coord[1]

        type = 'edge'

        closest_edge = -1
        min_moy_proxi_edge = sys.maxsize

        for i in range(len(self.env.edge_indices)):
            iA, iB = self.env.edge_indices[i]
            Ax, Ay = self.env.node_coords[iA]
            Bx, By = self.env.node_coords[iB]

            ABx = Bx - Ax
            ABy = By - Ay

            APx = px - Ax
            APy = py - Ay

            AB_len2 = ABx * ABx + ABy * ABy
            if AB_len2 == 0:
                dist = abs(APx) + abs(APy)
            else:
                t = (APx * ABx + APy * ABy) / AB_len2
                if t < 0:
                    t = 0
                elif t > 1:
                    t = 1

                Qx = Ax + t * ABx
                Qy = Ay + t * ABy

                proxi_x = abs(px - Qx)
                proxi_y = abs(py - Qy)
                dist = (proxi_x + proxi_y) / 2

            if dist < min_moy_proxi_edge:
                min_moy_proxi_edge = dist
                closest_edge = i

        return type, closest_edge

    def GetPathToTarget(self, request, context):
        if self.env is None or self.agent is None: return

        start_coord = request.start_coord
        target_coord = request.target_coord
        timestep = request.timestep

        start_type, start = self.GetClosestEntity(start_coord)
        target_type, target = self.GetClosestEntity(target_coord)

        start_node, target_node = self.GetClosestNodeFromEdgeToEdge(start, target)
    
        path = get_agent_path(self.env, self.agent, start_node, target_node, timestep)

        edges = [0] * (len(path) - 1)

        for i in range(len(path) - 1):
            edges[i] = self.env.G.edges[(path[i], path[i + 1])]["index"]

        return coord_service_pb2.PathResponse(edges=edges, start_type=start_type, start_index=start, target_type=target_type, target_index=target, message="Path found successfully : ")

if __name__ == "__main__":
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    coord_service_pb2_grpc.add_PathServiceServicer_to_server(GetPathServicer(), server)

    server.add_insecure_port("[::]:50051")

    server.start()
    server.wait_for_termination()
