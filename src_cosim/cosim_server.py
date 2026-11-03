import grpc
import torch
from concurrent import futures
from pathlib import Path

import coSim_pb2
import coSim_pb2_grpc
from google.protobuf import empty_pb2

from app import NetworkGraphEnvironment, DQNAgent, load_model, get_agent_path, get_nodes_distance


class CoSimServicer(coSim_pb2_grpc.CoSimServicer):
    """Implements the CoSim service defined in coSim.proto."""

    def __init__(self):
        self.env = None
        self.agent = None

    # ──────────────────────────────────────────────────────────────────────
    # rpc Start (Config) returns (google.protobuf.Empty)
    # ──────────────────────────────────────────────────────────────────────
    def Start(self, request, context):
        print(f"\n📥 Start(Config) called")
        print(f"  Config.path: '{request.path}'")

        try:
            if request.path and request.path.strip():
                BASE_DIR = Path(request.path)
            else:
                BASE_DIR = Path(__file__).resolve().parent.parent / "models"

            GRAPH_PATH = BASE_DIR / "final.h5"
            MODEL_PATH = BASE_DIR / "agent_final.pth"

            if not GRAPH_PATH.exists():
                raise FileNotFoundError(f"Graph file not found: {GRAPH_PATH}")
            if not MODEL_PATH.exists():
                raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

            env = NetworkGraphEnvironment(str(GRAPH_PATH), reward_type="combined")

            base_agent_config = {
                'state_size': 2 + 2 + 1 + 3 + 1 + env.max_neighbors * 5,
                'action_size': env.max_neighbors,
                'hidden_size': 512,
                'learning_rate': 1e-4,
                'gamma': 0.99,
                'epsilon_start': 0.01,
                'epsilon_end': 0.01,
                'epsilon_decay': 1.0,
                'memory_size': 20000,
                'batch_size': 128,
                'update_freq': 100,
                'device': 'cuda' if torch.cuda.is_available() else 'cpu'
            }

            final_model_agent = DQNAgent(**base_agent_config)
            agent = load_model(final_model_agent, str(MODEL_PATH))

            self.env = env
            self.agent = agent

            print(f"✓ Model loaded from {BASE_DIR}")
            print(f"📤 Returning Empty")
            return empty_pb2.Empty()

        except Exception as e:
            print(f"✗ Error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to start: {str(e)}")

    # ──────────────────────────────────────────────────────────────────────
    # rpc Finish (google.protobuf.Empty) returns (google.protobuf.Empty)
    # ──────────────────────────────────────────────────────────────────────
    def Finish(self, request, context):
        print(f"\n📥 Finish(Empty) called")
        self.env = None
        self.agent = None
        print(f"✓ Resources released")
        print(f"📤 Returning Empty")
        return empty_pb2.Empty()

    # ──────────────────────────────────────────────────────────────────────
    # rpc GetAttribute (Request) returns (Request)
    # ──────────────────────────────────────────────────────────────────────
    def GetAttribute(self, request, context):
        print(f"\n📥 GetAttribute(Request) called")
        print(f"  attribute:   {coSim_pb2.Request.Attribute.Name(request.attribute)} ({request.attribute})")
        print(f"  type:        {coSim_pb2.Request.RequestType.Name(request.type)} ({request.type})")
        print(f"  category:    {coSim_pb2.Request.Category.Name(request.category)} ({request.category})")
        print(f"  id:          '{request.id}'")
        print(f"  requestId:   '{request.requestId}'")
        if request.value.HasField("stringArray"):
            print(f"  value:       StringArray({list(request.value.stringArray.values)})")

        try:
            # Only ROUTE attribute on ROAD category is supported
            if request.attribute != coSim_pb2.Request.Attribute.ROUTE:
                context.abort(grpc.StatusCode.UNIMPLEMENTED, "Only ROUTE attribute is supported")
            if request.category != coSim_pb2.Request.Category.ROAD:
                context.abort(grpc.StatusCode.UNIMPLEMENTED, "Only ROAD category is supported")

            if self.env is None or self.agent is None:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Call Start RPC first")

            if not request.value or not request.value.HasField("stringArray"):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Expected stringArray in value field")

            edge_ids = request.value.stringArray.values
            if len(edge_ids) < 2:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Expected at least 2 edge IDs")

            try:
                start_edge = int(edge_ids[0])
                target_edge = int(edge_ids[1])
            except ValueError:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Edge IDs must be integers")

            num_edges = len(self.env.edge_indices)
            if not (0 <= start_edge < num_edges):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid start edge: {start_edge}")
            if not (0 <= target_edge < num_edges):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid target edge: {target_edge}")

            # Run the agent
            start_node, target_node = self._get_closest_nodes(start_edge, target_edge)
            path = get_agent_path(self.env, self.agent, start_node, target_node, timestep=0)

            edges = [
                str(self.env.G.edges[(path[i], path[i + 1])]["index"])
                for i in range(len(path) - 1)
            ]

            # Echo back same metadata + new path in value
            response = coSim_pb2.Request(
                attribute=request.attribute,
                forAll=request.forAll,
                type=request.type,
                category=request.category,
                id=request.id,
                value=coSim_pb2.ValueType(
                    stringArray=coSim_pb2.ValueType.StringArray(values=edges)
                ),
                subAttributeId=request.subAttributeId,
                requestId=request.requestId,
                timestamp=request.timestamp,
                entity_type=request.entity_type,
                message_type=request.message_type
            )

            print(f"📤 Returning Request with route: {edges}")
            return response

        except grpc.RpcError:
            raise
        except Exception as e:
            print(f"✗ Error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"GetAttribute failed: {str(e)}")

    # ──────────────────────────────────────────────────────────────────────
    # Unimplemented RPCs (defined in proto but not needed yet)
    # ──────────────────────────────────────────────────────────────────────
    def ExecuteOneTimeStep(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "ExecuteOneTimeStep not implemented")

    def GetManagedHosts(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "GetManagedHosts not implemented")

    def QueryRequest(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "QueryRequest not implemented")

    def SetAttribute(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "SetAttribute not implemented")

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────
    def _get_closest_nodes(self, start_edge, target_edge):
        """Find the closest endpoint nodes for the start and target edges."""
        start_nodes = [self.env.edge_indices[start_edge][0], self.env.edge_indices[start_edge][1]]
        target_nodes = [self.env.edge_indices[target_edge][0], self.env.edge_indices[target_edge][1]]

        best_start = start_nodes[0]
        best_target = target_nodes[0]
        min_distance = float('inf')

        for s in start_nodes:
            for t in target_nodes:
                dist = get_nodes_distance(self.env.G.nodes[s]["pos"], self.env.G.nodes[t]["pos"])
                if dist < min_distance:
                    min_distance = dist
                    best_start = s
                    best_target = t

        return best_start, best_target


if __name__ == "__main__":
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    coSim_pb2_grpc.add_CoSimServicer_to_server(CoSimServicer(), server)

    PORT = 50051
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"CoSim server listening on port {PORT}")
    server.wait_for_termination()
