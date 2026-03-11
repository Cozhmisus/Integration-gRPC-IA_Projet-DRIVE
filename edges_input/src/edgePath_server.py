import grpc
import torch
import sys
from concurrent import futures
from pathlib import Path

import getPath_service_pb2
import getPath_service_pb2_grpc

from app import NetworkGraphEnvironment, DQNAgent, load_model, get_agent_path, get_nodes_distance

class GetPathServicer(getPath_service_pb2_grpc.PathServiceServicer):
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

            return getPath_service_pb2.StartMessage(message="Success : Agent and Environement loaded successfully", numOfEdges=len(env.G.edges))
        
        except Exception as e:
            
            return getPath_service_pb2.StartMessage(message=f"Error : {e}" , numOfEdges=0)
        
    def EndEnv(self, request, context):
        self.env = None
        self.agent = None

        return getPath_service_pb2.EndMessage(message="Agent and Environement unloaded")
    
    def GetClosestNode(self, start_edge, target_edge):
        
        start_nodes = [self.env.edge_indices[start_edge][0], self.env.edge_indices[start_edge][1]]
        target_nodes = [self.env.edge_indices[target_edge][0], self.env.edge_indices[target_edge][1]]
        
        nodes_distances = []

        returned_start = 0
        returned_target = 0
        min_distance = sys.maxsize

        for start_node in start_nodes:
            for target_node in target_nodes:
                if get_nodes_distance(self.env.G.nodes[start_node]["pos"], self.env.G.nodes[target_node]["pos"]) < min_distance:
                    returned_start = start_node
                    returned_target = target_node

        return returned_start, returned_target

    def GetPathToTarget(self, request, context):
        if self.env is None or self.agent is None: return

        start_edge = request.start_edge
        target_edge = request.target_edge
        timestep = request.timestep

        start_node, target_node = self.GetClosestNode(start_edge, target_edge)

        path = get_agent_path(self.env, self.agent, start_node, target_node, timestep)

        edges = [0] * (len(path) - 1)

        for i in range(len(path) - 1):
            edges[i] = self.env.G.edges[(path[i], path[i + 1])]["index"]

        return getPath_service_pb2.PathToTarget(edges=edges)

if __name__ == "__main__":
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    getPath_service_pb2_grpc.add_PathServiceServicer_to_server(GetPathServicer(), server)

    server.add_insecure_port("[::]:50051")

    server.start()
    server.wait_for_termination()
