# AI gRPC Integration - DRIVE Project

## Project Overview
As part of the European DRIVE project, an AI system was developed to choose the most suitable path in a graph based on distance and connection capabilities.

This project aims to containerize this AI within a gRPC server in order to enable smooth communication between the simulation and the AI. The gRPC server had to respond to three commands:
- `start` — Used to initialize the simulation
- `ask` — Used to query the model
- `finish` — Used to terminate the simulation

## Usage
1. Start the server:
   ```bash
   docker run --rm -it -p 50051:50051 <server_container_name>
   ```

2. Start the client:
   ```bash
   docker run --rm -it <client_container_name> <server_IP_address>:50051
   ```

3. Initialize the simulation with the command:
   ```bash
   start
   ```

4. Query the agent with the command:
   ```bash
   ask
   ```

5. Send the start and destination nodes and receive the agent's response.

6. Stop the simulation with the command:
   ```bash
   end
   ```

7. Stop the client with the command:
   ```bash
   finish
   ```

## Why a gRPC Server?
For this project, we chose to use a gRPC server to ensure fast and flexible communication with the interface.

## Implementation
The final project is available in two different versions supporting two different input methods:
- A first version that takes a graph edge as input
- A second version that takes coordinates as input

In both cases, the output is a sequence of numbers representing the path (in edges) determined by the agent.

## Chosen Solution
Since the agent requires nodes as input, different methods for selecting the departure and destination nodes had to be studied among the four possible combinations resulting from the selection of two edges.

To achieve this, we created a simulation testing each possible combination and comparing the agent’s responses accordingly.

The results showed that choosing the nodes closest to each other provided the best outcomes. Distance appeared to be a determining factor, as the quality of the results decreased proportionally with the distance between the start and destination nodes.

---

# Integration gRPC IA - Projet DRIVE

## Présentation du projet
Dans le cadre du projet européen DRIVE, une IA ayant pour rôle de choisir le chemin le plus adapté dans un graph selon la distance et les capacités de connections a été développer.

Ce projet vise à conteneuriser cette IA dans un server gRPC afin de permettre une communication fluide entre la simulation et l'IA. Le server gRPC devait répondre à trois commande :
- `start` - Permettant d'initialiser la simulation
- `ask` - Permettant d'interroger le modèle
- `finish` - Permettant de mettre fin à la simulation

## Utilisation
1. Lancement du server :
   ```bash
   docker run --rm -it -p 50051:50051 <nom_conteneur_serveur>
   ```

2. Lancement du code client :
   ```bash
   docker run --rm -it <nom_conteneur_client> <addresse IP du server>:50051
   ```

3. Initialisation de la simulation avec la commande :
   ```bash
   start
   ```

4. Interrogation de l'agent avec la commande :
   ```bash
   ask
   ```

5. Envoi du noeud de départ et d'arrivée et retour de l'agent.

6. Arrêt de la simulation avec la commande :
   ```bash
   end
   ```

7. Arrêt du client avec la commande :
   ```bash
   finish
   ```

## Utilisation d'un server gRPC
Pour ce projet, nous avons décidé d'utiliser un server gRPC afin de permettre une communication performante et flexible avec l'interface.

## Réalisation
Le projet final se présente sous deux formes différentes permettant deux types d'input :
- Une première version prend une arête du graph en input
- Une deuxième version prend des coordonnées

Dans tous les cas, une chaîne de nombres est renvoyée, représentant le chemin (en arêtes) déterminé par l'agent.

## Solution trouvée
L'agent ayant besoin de noeuds en input, il a fallu étudier les différentes manières de sélectionner les noeuds de départ et d'arrivée parmi les quatre possibilités obtenues à partir de la sélection de deux arêtes.

Pour ce faire, nous avons créé une simulation testant chacune des possibilités et comparant les résultats des réponses de l'agent.

Il s'est avéré que choisir les noeuds les plus proches l'un de l'autre offrait les meilleurs résultats. La distance semble être un facteur déterminant, puisque les résultats devenaient proportionnellement moins bons à mesure que la distance entre les noeuds de départ et d'arrivée augmentait.
