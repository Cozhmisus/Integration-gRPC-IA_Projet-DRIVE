###################### IMPORT ######################


import h5py
import numpy as np
import networkx as nx
from typing import Dict, List, Tuple, Optional, Union
import torch
import torch.nn as nn
import torch.optim as optim
import random
from collections import deque, namedtuple, defaultdict
import heapq


###################### SERVER ######################


class NetworkGraphEnvironment:
    """
    Environment for path optimization in network graphs using reinforcement learning.
    
    This environment loads graphs from H5 files, provides observations that represent
    the current state, handles the action space with proper masking, and calculates
    rewards based on different objectives.
    """
    def __init__(self, h5_file_path: str, reward_type: str = 'distance', 
                 combined_weights: Dict[str, float] = None):
        """
        Initialize the environment with a graph from an H5 file.
        
        Args:
            h5_file_path: Path to the H5 file containing the graph data
            reward_type: Type of reward function ('distance', 'bandwidth', 'latency', 
                          'bandwidth_avg', 'combined')
            combined_weights: Weights for combined reward function (if reward_type is 'combined')
        """
        self.h5_file_path = h5_file_path
        self.reward_type = reward_type
        self.combined_weights = combined_weights or {'distance': 0.5, 'bandwidth': 0.25, 'latency': 0.25}
        
        # Load graph data from H5 file
        self._load_graph_data()
        
        # Build NetworkX graph for easy manipulation
        self._build_networkx_graph()
        
        # Initialize environment state
        self.current_node = None
        self.target_node = None
        self.visited_nodes = []
        self.path_history = []
        self.done = False
        self.path_metrics = {'distance': 0, 'bandwidth': float('inf'), 'latency': 0}
        
    def _load_graph_data(self):
        """Load graph data from H5 file with time series support."""
        with h5py.File(self.h5_file_path, 'r') as f:
            # Load node coordinates (static)
            self.node_coords = f['/metadata/nodes'][:]

            # Load edge indices (static)
            self.edge_indices = f['/metadata/edge_indices'][:]

            # Load base edge properties
            self.base_edge_distance = f['/distance'][:]
            
            # Load time series data
            self.bandwidth_time_series = f['/time_series/bandwidth'][:]
            self.latency_time_series = f['/time_series/latency'][:]
            
            # Get total number of timesteps
            self.total_timesteps = f['/time_series/parameters/total_timesteps'][()]
            
            # Initialize current timestep (for fixed case, always 0)
            self.current_timestep = 0
            
            # Get current time properties
            self.edge_bandwidth = self.bandwidth_time_series[self.current_timestep, :]
            self.edge_latency = self.latency_time_series[self.current_timestep, :]
            self.edge_distance = self.base_edge_distance  # Distance is static
            
            # Load or calculate min/max values across all timesteps
            if '/stats/min_bandwidth' in f:
                self.bandwidth_min = f['/stats/min_bandwidth'][()]
                self.bandwidth_max = f['/stats/max_bandwidth'][()]
                self.latency_min = f['/stats/min_latency'][()]
                self.latency_max = f['/stats/max_latency'][()]
                self.distance_min = f['/stats/min_distance'][()]
                self.distance_max = f['/stats/max_distance'][()]
            else:
                # Calculate min/max across all timesteps
                self.bandwidth_min = np.min(self.bandwidth_time_series)
                self.bandwidth_max = np.max(self.bandwidth_time_series)
                self.latency_min = np.min(self.latency_time_series)
                self.latency_max = np.max(self.latency_time_series)
                self.distance_min = np.min(self.edge_distance)
                self.distance_max = np.max(self.edge_distance)
    def _build_networkx_graph(self):
        """Build a NetworkX graph from the loaded data at the current timestep."""
        self.G = nx.Graph()

        # Add nodes
        for i, coords in enumerate(self.node_coords):
            self.G.add_node(i, pos=coords)

        # Add edges with properties at the current timestep
        for i, (src, dst) in enumerate(self.edge_indices):
            self.G.add_edge(src, dst,
                        bandwidth=self.edge_bandwidth[i],
                        latency=self.edge_latency[i],
                        distance=self.edge_distance[i],
                        index=i)

        # Calculate number of nodes and max number of neighbors
        self.num_nodes = len(self.node_coords)
        self.max_neighbors = max(len(list(self.G.neighbors(node))) for node in self.G.nodes())
    
    def _update_graph_properties(self, timestep=None):
        """Update graph edge properties for the specified timestep."""
        if timestep is not None:
            self.current_timestep = timestep
        
        # Clip timestep to valid range
        self.current_timestep = max(0, min(self.current_timestep, self.total_timesteps - 1))
        
        # Update edge properties
        self.edge_bandwidth = self.bandwidth_time_series[self.current_timestep, :]
        self.edge_latency = self.latency_time_series[self.current_timestep, :]
        
        # Update graph edges
        for i, (src, dst) in enumerate(self.edge_indices):
            self.G[src][dst]['bandwidth'] = self.edge_bandwidth[i]
            self.G[src][dst]['latency'] = self.edge_latency[i]
            # Distance remains unchanged (static)

    def reset(self, start_node=None, target_node=None, timestep=None):
        """
        Reset the environment with optional specific start and target nodes and timestep.

        Args:
            start_node: Starting node index (random if None)
            target_node: Target node index (random if None)
            timestep: Timestep to use for the graph properties (default: 0)

        Returns:
            Initial state observation
        """
        # Select random start and target nodes if not specified
        if start_node is None:
            start_node = np.random.randint(0, self.num_nodes - 1)
        if target_node is None:
            target_node = np.random.randint(0, self.num_nodes - 1)
            # Ensure target is different from start
            while target_node == start_node:
                target_node = np.random.randint(0, self.num_nodes - 1)

        # Select a random timestep between 0 and 300 if not specified
        if timestep is None:
            timestep = np.random.randint(0, min(300, self.total_timesteps))

        # Set current timestep and update graph properties
        self._update_graph_properties(timestep)
        
        self.current_node = start_node
        self.target_node = target_node
        self.visited_nodes = [start_node]
        self.path_history = []
        self.done = False
        self.path_metrics = {'distance': 0, 'bandwidth': float('inf'), 'latency': 0}
        
        # For fixed time instance, we don't advance time with steps   ( this is not used yet )
        self.starting_timestep = self.current_timestep
        
        return self._get_observation()
    
    def _get_observation(self):
        """
        Get the current state observation.

        Returns:
            State observation as a numpy array containing:
            - Current node features
            - Target node features
            - Distance to target
            - Path metrics so far
            - Features of neighboring nodes
            - Current timestep information (new)
        """
        # Current node features
        current_coords = self.node_coords[self.current_node]

        # Target node features
        target_coords = self.node_coords[self.target_node]

        # Distance to target (Euclidean in coordinate space)
        dist_to_target = np.linalg.norm(current_coords - target_coords)

        # Initialize neighbor features
        # [node_idx, normalized_bandwidth, normalized_latency, normalized_distance, visited_flag]
        neighbor_features = np.zeros((self.max_neighbors, 5))

        neighbors = list(self.G.neighbors(self.current_node))
        for i, neighbor in enumerate(neighbors):
            if i >= self.max_neighbors:
                break

            # Get edge properties
            edge_data = self.G[self.current_node][neighbor]

            # Normalize edge properties
            norm_bandwidth = (edge_data['bandwidth'] - self.bandwidth_min) / (self.bandwidth_max - self.bandwidth_min)
            norm_latency = (edge_data['latency'] - self.latency_min) / (self.latency_max - self.latency_min)
            norm_distance = (edge_data['distance'] - self.distance_min) / (self.distance_max - self.distance_min)

            # Check if neighbor has been visited
            visited = 1.0 if neighbor in self.visited_nodes else 0.0

            # Store features
            neighbor_features[i] = [neighbor, norm_bandwidth, norm_latency, norm_distance, visited]

        # Normalize path metrics so far
        norm_path_distance = self.path_metrics['distance'] / (self.distance_max * self.num_nodes)
        norm_path_bandwidth = self.path_metrics['bandwidth'] / self.bandwidth_max if self.path_metrics['bandwidth'] != float('inf') else 1.0
        norm_path_latency = self.path_metrics['latency'] / (self.latency_max * self.num_nodes)
        
        # Time feature: normalized current timestep
        norm_timestep = self.current_timestep / (self.total_timesteps - 1) if self.total_timesteps > 1 else 0

        # Combine all features into one observation vector
        observation = np.concatenate([
            current_coords,  # Current node coordinates
            target_coords,   # Target node coordinates
            [dist_to_target],  # Distance to target
            [norm_path_distance, norm_path_bandwidth, norm_path_latency],  # Path metrics
            [norm_timestep],  # Current time information (new)
            neighbor_features.flatten()  # Neighbor features
        ])

        return observation
    def calculate_path_metrics(self, path: List[int]) -> Dict[str, float]:
        """
        Calculate metrics for a given path.
        
        Args:
            path: List of nodes in the path
            
        Returns:
            Path metrics (distance, bandwidth, latency)
        """
        metrics = {'distance': 0, 'bandwidth': float('inf'), 'latency': 0}
        
        # Save the current timestep
        original_timestep = self.current_timestep
        
        # Start from time 0
        current_time = 0
        self._update_graph_properties(current_time)

        try:
            for i in range(len(path) - 1):
                src, dst = path[i], path[i + 1]
                
                # Calculate travel time
                travel_time = self._calculate_travel_time(src, dst)
                
                # Advance time
                current_time = min(current_time + travel_time, self.total_timesteps - 1)
                self._update_graph_properties(current_time)
                
                # Get edge properties after time advancement
                edge_data = self.G[src][dst]
                
                # Update metrics
                metrics['distance'] += edge_data['distance']
                metrics['bandwidth'] = min(metrics['bandwidth'], edge_data['bandwidth'])
                metrics['latency'] += edge_data['latency']
        finally:
            # Restore original timestep
            self._update_graph_properties(original_timestep)
        
        return metrics
    def get_action_mask(self) -> np.ndarray:
        """
        Get a mask of valid actions (neighbors that can be visited).
        
        Returns:
            Boolean mask where True indicates a valid action
        """
        mask = np.zeros(self.max_neighbors, dtype=bool)
        
        neighbors = list(self.G.neighbors(self.current_node))
        for i, neighbor in enumerate(neighbors):
            if i >= self.max_neighbors:
                break
            # Action is valid if the neighbor hasn't been visited or is the target
            mask[i] = (neighbor not in self.visited_nodes) or (neighbor == self.target_node)
        
        return mask
    
    def step(self, action):
        """
        Take a step in the environment by choosing a neighbor to visit.
        Time advances based on the travel time between nodes.

        Args:
            action: Index of the neighbor to visit

        Returns:
            observation: New state observation
            reward: Reward for the action
            done: Whether the episode is done
            info: Additional information
        """
        if self.done:
            return self._get_observation(), 0.0, True, {"message": "Episode already done"}

        # Get the actual neighbor node from the action index
        neighbors = list(self.G.neighbors(self.current_node))
        if action >= len(neighbors):
            # Invalid action (no neighbor at this index)
            return self._get_observation(), -10.0, self.done, {"message": "Invalid action"}

        next_node = neighbors[action]

        # Calculate travel time to next node
        travel_time = self._calculate_travel_time(self.current_node, next_node)
        
        # Advance time
        new_timestep = min(self.current_timestep + travel_time, self.total_timesteps - 1)
        self._update_graph_properties(new_timestep)
        
        # Get edge properties AFTER updating the time
        # This represents the network state upon arrival at the next node
        edge_data = self.G[self.current_node][next_node]

        # Update path metrics
        self.path_metrics['distance'] += edge_data['distance']
        self.path_metrics['bandwidth'] = min(self.path_metrics['bandwidth'], edge_data['bandwidth'])
        self.path_metrics['latency'] += edge_data['latency']

        # Store the transition with time information
        self.path_history.append((self.current_node, next_node, edge_data, self.current_timestep))

        # Move to the next node
        self.current_node = next_node
        self.visited_nodes.append(next_node)

        # Check if we've reached the target
        if next_node == self.target_node:
            self.done = True
            # Bonus reward for reaching the target
            target_reward = 10.0
        else:
            target_reward = 0.0

        # Calculate reward based on the reward type
        step_reward = self._calculate_reward()
        reward = step_reward + target_reward

        # Get the new observation
        observation = self._get_observation()

        # Check for loops or too long paths
        if len(self.visited_nodes) > 2 * self.num_nodes:
            self.done = True
            reward -= 5.0  # Penalty for too long path

        # Add time information to the info dict
        info = {
            "path_metrics": self.path_metrics,
            "current_timestep": self.current_timestep,
            "travel_time": travel_time
        }

        return observation, reward, self.done, info
    
    def _calculate_reward(self) -> float:
        """
        Calculate the reward based on the chosen reward type.
        
        Returns:
            Reward value
        """
        if not self.path_history:
            return 0.0
            
        last_edge = self.path_history[-1][2]
        
        if self.reward_type == 'distance':
            # Negative reward based on distance (scaled)
            normalized_distance = last_edge['distance'] / self.distance_max
            return -normalized_distance
        
        elif self.reward_type == 'bandwidth':
            # Reward based on bandwidth (bottleneck)
            normalized_bandwidth = (last_edge['bandwidth'] - self.bandwidth_min) / (self.bandwidth_max - self.bandwidth_min)
            return normalized_bandwidth
        
        elif self.reward_type == 'bandwidth_avg':
            # Reward based on average bandwidth
            avg_bandwidth = sum(edge['bandwidth'] for _, _, edge in self.path_history) / len(self.path_history)
            normalized_avg_bandwidth = (avg_bandwidth - self.bandwidth_min) / (self.bandwidth_max - self.bandwidth_min)
            return normalized_avg_bandwidth
        
        elif self.reward_type == 'latency':
            # Negative reward based on latency
            normalized_latency = last_edge['latency'] / self.latency_max
            return -normalized_latency
        elif self.reward_type == 'bandwidth_overall':
            normalized_bandwidth = last_edge['bandwidth'] / self.bandwidth_max
            return normalized_bandwidth
        
        elif self.reward_type == 'combined':
            # Weighted combination of rewards            
            normalized_distance = last_edge['distance'] / self.distance_max
            # normalized_bandwidth = (last_edge['bandwidth'] - self.bandwidth_min) / (self.bandwidth_max - self.bandwidth_min)
            normalized_bandwidth = last_edge['bandwidth'] / self.bandwidth_max
            normalized_latency = last_edge['latency'] / self.latency_max
            
            distance_reward = -normalized_distance * self.combined_weights['distance']
            bandwidth_reward = normalized_bandwidth * self.combined_weights['bandwidth']
            latency_reward = -normalized_latency * self.combined_weights['latency']
            
            return distance_reward + bandwidth_reward + latency_reward
        
        else:
            raise ValueError(f"Unknown reward type: {self.reward_type}")
    def _calculate_travel_time(self, source, target):
        """
        Calculate the time it takes to traverse from source to target node.
        
        For simplicity, we'll use the distance divided by some speed factor
        to determine travel time in seconds (timesteps).
        
        Args:
            source: Source node
            target: Target node
            
        Returns:
            Number of timesteps required to traverse the edge
        """
        # Get the edge distance
        distance = self.G[source][target]['distance']
        
        # Assume a speed factor (distance units per timestep)
        # You might want to adjust this based on your graph scale
        speed_factor = 10.0
        
        # Calculate travel time in timesteps (rounded to nearest integer)
        travel_time = int(round(distance / speed_factor))
        
        # Ensure minimum of 1 timestep
        travel_time = max(1, travel_time)
        
        return travel_time

    def get_optimal_path(self, metric: str = 'distance', start_node=None, target_node=None, timestep=None):
        """
        Get the optimal path according to a specific metric for comparison.
        
        Args:
            metric: The metric to optimize ('distance', 'bandwidth', 'latency')
            start_node: Starting node (uses current_node if None)
            target_node: Target node (uses target_node if None)
            timestep: Starting timestep (uses current_timestep if None)
                
        Returns:
            List of nodes representing the optimal path
        """
        # Use current state if not specified
        if start_node is None:
            start_node = self.current_node
        if target_node is None:
            target_node = self.target_node
        if timestep is None:
            timestep = self.current_timestep
        
        # Save current state to restore later
        original_node = self.current_node
        original_timestep = self.current_timestep
        original_visited = self.visited_nodes.copy()
        original_path_metrics = self.path_metrics.copy()
        
        try:
            # Set up for path finding with specified parameters
            self._update_graph_properties(timestep)
            
            if metric == 'distance':
                # Use standard Dijkstra's algorithm for shortest path by distance
                path = nx.shortest_path(self.G, start_node, target_node, weight='distance')
                
            elif metric == 'latency':
                # Use Dijkstra's algorithm for lowest latency path
                path = nx.shortest_path(self.G, start_node, target_node, weight='latency')
                
            elif metric == 'bandwidth':
                # For bandwidth, we want to maximize the minimum bandwidth along the path
                # We'll use a modified approach to find maximum bottleneck bandwidth path
                
                # Initialize
                bandwidths = {node: 0 if node == start_node else float('-inf') for node in self.G.nodes}
                predecessors = {node: None for node in self.G.nodes}
                visited = set()
                
                # Priority queue (using negative bandwidth for max-heap)
                pq = [(-bandwidths[start_node], start_node)]
                
                while pq:
                    # Get node with highest bandwidth
                    current_bw, current = heapq.heappop(pq)
                    current_bw = -current_bw  # Convert back to positive
                    
                    # If we reached the target, we're done
                    if current == target_node:
                        break
                    
                    # Skip if already visited
                    if current in visited:
                        continue
                    
                    visited.add(current)
                    
                    # Check all neighbors
                    for neighbor in self.G.neighbors(current):
                        if neighbor in visited:
                            continue
                            
                        # Calculate bottleneck bandwidth
                        edge_bw = self.G[current][neighbor]['bandwidth']
                        new_bw = min(current_bw, edge_bw) if current != start_node else edge_bw
                        
                        # If we found a better path, update
                        if new_bw > bandwidths[neighbor]:
                            bandwidths[neighbor] = new_bw
                            predecessors[neighbor] = current
                            heapq.heappush(pq, (-new_bw, neighbor))
                
                # Reconstruct the path
                if predecessors[target_node] is None:
                    raise nx.NetworkXNoPath(f"No path between {start_node} and {target_node}")
                    
                path = [target_node]
                while path[-1] != start_node:
                    path.append(predecessors[path[-1]])
                
                path = list(reversed(path))
                
            else:
                raise ValueError(f"Unknown metric: {metric}")
            
            return path
            
        finally:
            # Restore original state
            self.current_node = original_node
            self._update_graph_properties(original_timestep)
            self.visited_nodes = original_visited
            self.path_metrics = original_path_metrics

Transition = namedtuple('Transition', ('state', 'action', 'reward', 'next_state', 'done', 'action_mask'))

class ReplayMemory:
    """
    Replay memory for storing and sampling transitions.
    """
    def __init__(self, capacity: int):
        """
        Initialize the replay memory.
        
        Args:
            capacity: Maximum capacity of the memory
        """
        self.capacity = capacity
        self.memory = []
        self.position = 0
    
    def push(self, state: np.ndarray, action: int, reward: float, 
             next_state: np.ndarray, done: bool, action_mask: np.ndarray) -> None:
        """
        Store a transition in the memory.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether the episode is done
            action_mask: Mask of valid actions for the next state
        """
        if len(self.memory) < self.capacity:
            self.memory.append(None)
        self.memory[self.position] = Transition(state, action, reward, next_state, done, action_mask)
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size: int) -> List[Transition]:
        """
        Sample a batch of transitions from the memory.
        
        Args:
            batch_size: Size of the batch to sample
            
        Returns:
            List of sampled transitions
        """
        return random.sample(self.memory, batch_size)
    
    def __len__(self) -> int:
        """Get the current size of the memory."""
        return len(self.memory)

class DuelingDQN(nn.Module):
    """
    Dueling DQN architecture for improved performance.
    
    This architecture separates the value and advantage streams, which helps the agent
    learn which actions are valuable in which states more effectively.
    """
    def __init__(self, state_size: int, action_size: int, hidden_size: int = 256):
        """
        Initialize the Dueling DQN model.
        
        Args:
            state_size: Dimension of the state space
            action_size: Dimension of the action space
            hidden_size: Size of hidden layers
        """
        super(DuelingDQN, self).__init__()
        
        # Feature extraction layers
        self.feature_layer = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU()
        )
        
        # Value stream
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1)
        )
        
        # Advantage stream
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, action_size)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor
            
        Returns:
            Q-values for each action
        """
        features = self.feature_layer(x)
        
        value = self.value_stream(features)
        advantages = self.advantage_stream(features)
        
        # Combine value and advantages using the dueling architecture
        # Q(s,a) = V(s) + (A(s,a) - mean(A(s,a')))
        q_values = value + (advantages - advantages.mean(dim=1, keepdim=True))
        
        return q_values

class DQNAgent:
    """
    Deep Q-Network agent for path optimization in network graphs.
    
    This implementation includes several advanced techniques:
    - Dueling DQN architecture
    - Experience replay
    - Target network updates
    - Action masking for invalid actions
    - Epsilon-greedy exploration with annealing
    """
    def __init__(self, state_size: int, action_size: int, 
                 hidden_size: int = 256, learning_rate: float = 1e-4,
                 gamma: float = 0.99, epsilon_start: float = 1.0,
                 epsilon_end: float = 0.01, epsilon_decay: float = 0.9995,
                 memory_size: int = 10000, batch_size: int = 64,
                 update_freq: int = 10, device: str = 'cuda'):
        """
        Initialize the DQN agent.
        
        Args:
            state_size: Dimension of the state space
            action_size: Dimension of the action space
            hidden_size: Size of hidden layers in the neural network
            learning_rate: Learning rate for the optimizer
            gamma: Discount factor
            epsilon_start: Initial exploration rate
            epsilon_end: Final exploration rate
            epsilon_decay: Rate of exploration decay
            memory_size: Size of the replay memory
            batch_size: Batch size for training
            update_freq: Frequency of target network updates
            device: Device to run the model on ('cuda' or 'cpu')
        """
        self.state_size = state_size
        self.action_size = action_size
        self.hidden_size = hidden_size
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.memory_size = memory_size
        self.batch_size = batch_size
        self.update_freq = update_freq
        self.episode_start = None
        
        # Set device
        self.device = torch.device(device if torch.cuda.is_available() and device == 'cuda' else 'cpu')
        
        # Initialize networks
        self.policy_net = DuelingDQN(state_size, action_size, hidden_size).to(self.device)
        self.target_net = DuelingDQN(state_size, action_size, hidden_size).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()  # Target network is only used for inference
        
        # Initialize optimizer
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
        
        # Initialize replay memory
        self.memory = ReplayMemory(memory_size)
        
        # Initialize step counter for target network updates
        self.steps = 0
    
    def select_action(self, state: np.ndarray, action_mask: np.ndarray, 
                      epsilon: Optional[float] = None) -> int:
        """
        Select an action using epsilon-greedy policy with action masking.
        
        Args:
            state: Current state
            action_mask: Mask of valid actions
            epsilon: Exploration rate (uses self.epsilon if None)
            
        Returns:
            Selected action
        """
        if epsilon is None:
            epsilon = self.epsilon
        
        # Check if there are any valid actions
        if not np.any(action_mask):
            # No valid actions, return a random action (will be handled by environment)
            return random.randint(0, self.action_size - 1)
        
        if random.random() <= epsilon:
            # Exploration: select a random valid action
            valid_actions = np.where(action_mask)[0]
            return np.random.choice(valid_actions)
        else:
            # Exploitation: select the best valid action
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
                q_values = self.policy_net(state_tensor)
                
                # Mask invalid actions with a large negative value
                masked_q_values = q_values.clone()
                masked_q_values[0, ~torch.tensor(action_mask, device=self.device)] = -1e9
                
                return masked_q_values.max(1)[1].item()
    
    def store_transition(self, state: np.ndarray, action: int, reward: float, 
                         next_state: np.ndarray, done: bool, action_mask: np.ndarray) -> None:
        """
        Store a transition in the replay memory.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether the episode is done
            action_mask: Mask of valid actions for the next state
        """
        self.memory.push(state, action, reward, next_state, done, action_mask)
    
    def update(self) -> float:
        """
        Update the model using a batch of experiences from the replay memory.
        
        Returns:
            Loss value
        """
        if len(self.memory) < self.batch_size:
            return 0.0
        
        # Sample a batch of transitions from the replay memory
        transitions = self.memory.sample(self.batch_size)
        batch = Transition(*zip(*transitions))
        
        # Convert to tensors
        state_batch = torch.FloatTensor(np.array(batch.state)).to(self.device)
        action_batch = torch.LongTensor(batch.action).unsqueeze(1).to(self.device)
        reward_batch = torch.FloatTensor(batch.reward).to(self.device)
        next_state_batch = torch.FloatTensor(np.array(batch.next_state)).to(self.device)
        done_batch = torch.FloatTensor(batch.done).to(self.device)
        action_mask_batch = torch.BoolTensor(np.array(batch.action_mask)).to(self.device)
        
        # Compute Q(s_t, a) - the model computes Q(s_t), then we select the columns of actions taken
        q_values = self.policy_net(state_batch).gather(1, action_batch)
        
        # Compute V(s_{t+1}) for all next states - double DQN approach
        next_q_values = torch.zeros(self.batch_size, device=self.device)
        with torch.no_grad():
            # Select actions using policy network
            policy_q_values = self.policy_net(next_state_batch)
            
            # Apply action masking
            for i in range(self.batch_size):
                policy_q_values[i, ~action_mask_batch[i]] = -1e9
                
            # Get best actions from policy network
            next_actions = policy_q_values.max(1)[1].unsqueeze(1)
            
            # Get values from target network using these actions
            next_q_values = self.target_net(next_state_batch).gather(1, next_actions).squeeze(1)
        
        # Compute the expected Q values: Q(s,a) = r + gamma * max_a' Q(s',a')
        expected_q_values = reward_batch + (1 - done_batch) * self.gamma * next_q_values
        
        # Compute Huber loss (more robust than MSE)
        loss = nn.SmoothL1Loss()(q_values.squeeze(), expected_q_values)
        
        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        
        # Clip gradients to prevent exploding gradients
        for param in self.policy_net.parameters():
            param.grad.data.clamp_(-1, 1)
            
        self.optimizer.step()
        
        # Update target network
        self.steps += 1
        if self.steps % self.update_freq == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
        
        # # Update exploration rate
        if self.episode_start:
            self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        
        return loss.item()
    
    def save(self, path: str) -> None:
        """
        Save the model to a file.
        
        Args:
            path: Path to save the model
        """
        torch.save({
            'policy_net': self.policy_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'steps': self.steps
        }, path)
    
    def load(self, path: str) -> None:
        """
        Load the model from a file.
        
        Args:
            path: Path to load the model from
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint['policy_net'])
        self.target_net.load_state_dict(checkpoint['target_net'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint['epsilon']
        self.steps = checkpoint['steps']

def load_model(agent, model_path):
    """Load a saved model into an agent."""
    checkpoint = torch.load(model_path, map_location=agent.device)
    agent.policy_net.load_state_dict(checkpoint['policy_net'])
    agent.target_net.load_state_dict(checkpoint['target_net'])
    agent.optimizer.load_state_dict(checkpoint['optimizer'])
    agent.epsilon = checkpoint['epsilon']
    agent.steps = checkpoint['steps']
    return agent

def get_agent_path(env, agent, start_node, target_node, timestep):
    """
    Get the path taken by the agent from start to target.
    
    Args:
        env: NetworkGraphEnvironment
        agent: DQNAgent
        start_node: Starting node index
        target_node: Target node index
        timestep: Starting timestep
        
    Returns:
        Tuple of (path, path_metrics)
    """
    # Reset to the given start and target
    state = env.reset(start_node=start_node, target_node=target_node, timestep=timestep)
    action_mask = env.get_action_mask()
    
    path = [env.current_node]
    
    max_steps = 2 * env.num_nodes  # Maximum steps to prevent infinite loops
    
    for step in range(max_steps):
        # Select action (epsilon = 0 for evaluation)
        action = agent.select_action(state, action_mask, epsilon=0.0)
        next_state, _, done, info = env.step(action)
        
        state = next_state
        action_mask = env.get_action_mask()
        
        path.append(env.current_node)
        
        if done:
            break
    
    # Verify path validity (this is safer than using calculate_path_metrics)
    valid_path = True
    for i in range(len(path) - 1):
        if path[i+1] not in list(env.G.neighbors(path[i])):
            valid_path = False
            break
    
    if not valid_path:
        # Return a safe fallback if path is invalid
        return [start_node]
    
    return path

def get_nodes_distance(pos_1, pos_2):
    """
    Calculate the distance between two coordinates in the form of a tuple.
    
    Args:
        pos_1: Coordinates of the first object
        pos_2: Coordinates of the second object

    Returns:
        Distance between the two coordinates.
    """

    distance_x = abs(pos_1[0] - pos_2[0])
    distance_y = abs(pos_1[1] - pos_2[1])
    
    return pow(pow(distance_x, 2) + pow(distance_y, 2), 0.5)