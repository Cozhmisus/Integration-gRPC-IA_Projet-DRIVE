# AI gRPC Integration — DRIVE Project (CoSim version)

## Project Overview

As part of the European **DRIVE** project, an AI agent was trained to find the most suitable path through a road network graph, optimizing across distance, bandwidth, and latency.

This project wraps that AI inside a **gRPC server** that speaks the **CoSim protocol** (`coSim.proto`), so it can be coupled with the **CoSiFra co-simulation framework**. The server receives a starting edge ID and a destination edge ID, runs the trained DQN agent, and returns the full list of edges forming the route.

---

## Architecture

```
┌─────────────────┐      gRPC (port 50051)      ┌─────────────────────┐
│  Co-Simulator   │  ◄──────────────────────►   │  CoSim gRPC Server  │
│  (or client)    │      coSim.proto            │  (cosim_server.py)  │
└─────────────────┘                             │      + DQN Agent    │
                                                └─────────────────────┘
```

The server implements the `CoSim` service from `protos/coSim.proto` with three active RPCs:

| RPC | Input | Output | Purpose |
|---|---|---|---|
| `Start` | `Config` | `Empty` | Loads the model and graph into memory |
| `GetAttribute` | `Request` (with start/end edge IDs) | `Request` (with edge path) | Computes a route |
| `Finish` | `Empty` | `Empty` | Releases the model |

Other RPCs (`ExecuteOneTimeStep`, `GetManagedHosts`, `QueryRequest`, `SetAttribute`) are defined in the proto but return `UNIMPLEMENTED` for now.

---

## Inputs Explained

### Edge IDs
The numbers passed as `startEdgeId` and `destEdgeId` are **integer IDs** representing edges in the road network graph. These IDs come from a normalization step performed when the SUMO map was converted into the `final.h5` file — each edge in the original SUMO network was assigned a unique integer index.

- **Valid range:** `0` to `227` (the graph has **228 edges**)
- **Format:** strings in the gRPC `StringArray`, e.g. `["0", "10"]`

### Timestep (optional)
The model handles a time-varying graph (bandwidth and latency change over time). You can optionally pass a `timestamp` field with the request to query the network at a specific moment.

- **Valid range:** `0` to `1199` (the time series has **1200 timesteps**)
- **Default:** `0.0` if not provided
- **Recommended:** `0` to `299` (this is the range the model was primarily trained on)

### Other fields (per `coSim.proto`)
- `attribute` must be `ROUTE` (value `1`)
- `category` must be `ROAD` (value `2`)
- `type` must be `GET` (value `0`)
- `id`: any string — vehicle ID assigned by the client
- `requestId`: any string — unique request ID

---

## Quick Start

### Option 1 — Run locally

```bash
# 1. Install dependencies
cd edges_input
pip install -r requirements.txt
pip install torch networkx h5py

# 2. Generate the protobuf stubs (only needed once)
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./src_cosim \
    --grpc_python_out=./src_cosim \
    protos/coSim.proto

# 3. Start the server (terminal 1)
cd src_cosim
python cosim_server.py
# → "CoSim server listening on port 50051"

# 4. Start the client (terminal 2)
cd src_cosim
python cosim_client.py
# Or, to connect to a different host:
python cosim_client.py 192.168.1.100:50051
```

### Option 2 — Run with Docker

```bash
# Build
docker build -f Dockerfile.server -t edge-cosim .

# Run
docker run --rm -p 50051:50051 edge-cosim
```

---

## Client Commands

The interactive client mirrors the proto RPCs directly:

| Command | Calls RPC | Description |
|---|---|---|
| `Start` | `Start(Config)` | Initialize the model on the server |
| `GetAttribute` | `GetAttribute(Request)` | Query a route between two edges |
| `Finish` | `Finish(Empty)` | Release the model on the server |
| `exit` | — | Close the client (no RPC call) |

### Typical workflow

1. `Start` — once, to load the model
2. `GetAttribute` — as many times as you need
3. `Finish` — once, to clean up
4. `exit` — to close the client

---

## Example Session

```
$ python cosim_client.py
Connected to CoSim server at localhost:50051
Available RPCs: Start, GetAttribute, Finish, exit

Enter RPC to call (Start/GetAttribute/Finish/exit): Start

📤 Sending Start(Config):
  Config.path: ''

📥 Received Empty response
✓ Start RPC completed

Enter RPC to call (Start/GetAttribute/Finish/exit): GetAttribute
Enter starting edge ID and destination edge ID: 0 10
Enter timestamp (optional, press Enter for 0.0):

📤 Sending GetAttribute(Request):
  attribute:    ROUTE (1)
  forAll:       False
  type:         GET (0)
  category:     ROAD (2)
  id:           'vehicle_1'
  value:        StringArray(['0', '10'])
  requestId:    'req_0_10'
  timestamp:    0.0
  entity_type:  CAR (0)

📥 Received GetAttribute response (Request):
  attribute:    ROUTE (1)
  type:         GET (0)
  category:     ROAD (2)
  id:           'vehicle_1'
  value:        StringArray(['221', '144', '143', '42', '44', '170'])
  requestId:    'req_0_10'

✓ Route from edge 0 to edge 10:
  221 → 144 → 143 → 42 → 44 → 170
  Total edges: 6

Enter RPC to call (Start/GetAttribute/Finish/exit): GetAttribute
Enter starting edge ID and destination edge ID: 50 200
Enter timestamp (optional, press Enter for 0.0): 100

📤 Sending GetAttribute(Request):
  ...
  timestamp:    100.0
  ...
✓ Route from edge 50 to edge 200:
  ...

Enter RPC to call (Start/GetAttribute/Finish/exit): Finish

📤 Sending Finish(Empty)

📥 Received Empty response
✓ Finish RPC completed

Enter RPC to call (Start/GetAttribute/Finish/exit): exit
Exiting client
```

---

## How the Routing Works

The agent requires **nodes** as input but the co-sim sends **edges**. Since each edge has two endpoint nodes, there are four possible (start-node, target-node) combinations from any (start-edge, target-edge) pair.

We tested all four combinations and found that choosing the **pair of nodes closest to each other** gave the best results — the quality of the agent's output decreases as the distance between the chosen start and target nodes grows. This is implemented in `_get_closest_nodes()` in `cosim_server.py`.

Once the closest pair is selected, the trained DQN agent is rolled out from the start node to the target node. The resulting node sequence is then converted back to edge IDs and returned in the response.

---

## File Layout

```
edges_input/
├── protos/
│   └── coSim.proto                 # CoSim service definition
├── src_cosim/
│   ├── app.py                      # AI logic (environment + DQN agent)
│   ├── cosim_server.py             # gRPC server (CoSim service)
│   ├── cosim_client.py             # Interactive test client
│   └── coSim_pb2*.py               # Generated stubs
├── models/
│   ├── final.h5                    # Road network graph (50 nodes, 228 edges, 1200 timesteps)
│   └── agent_final.pth             # Trained DQN weights
├── requirements.txt
├── Dockerfile.server
└── README (1).md                   # This file
```

---

## Why gRPC?

gRPC was chosen for its low-latency, strongly-typed, language-agnostic communication — a good fit for coupling a Python AI service with the CoSiFra co-simulation framework over the network.
