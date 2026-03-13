# Integration gRPC IA - Projet DRIVE

## Présentation du projet
Dans le cadre du projet européen DRIVE, une IA ayant pour rôle de choisir le chemin le plus adapté dans un graph selon la distance et les capacités de connections a été développer.
Ce projet vise à conteneuriser cette IA dans un server gRPC afin de permettre une communication fluide entre la simulation et l'IA. Le server gRPC devait répondre à trois commande : Start - Permettant de initialiser la simulation / ask - Permettant d'interroger le modèle / finish - Permettant de mettre fin à la simulation.

## Utilisation
1. Lancement du server : ```docker run --rm -it -p 50051:50051 <nom_conteneur_serveur>```
3. Lancement du code client : ```docker run --rm -it <nom_conteneur_client> <addresse IP du server>:50051```
4. Initialisation de la simulation avec la commande : ```start```
5. Interrogation de l'agent avec la commande : ```ask```
6. Envoie du noeud de départ et d'arrivée et retour de l'agent
7. Arrêt de la simulation avec la commande : ```end```
8. Arrêt du client avec la commande : ```finish```

## Utilisation d'un server gRPC
Pour ce projet, nous avons décider d'utiliser un server gRPC pour permettre à la communication avec l'interface d'être performante et fléxible.

## Réalisation 
Le projet final se présente sous deux forme différentes permettant deux input différent.
Une première version prend une arrête du graph en input tandis qu'une deuxième prend des coordonnées.

Dans tout les cas, une chaîne de nombres est renvoyé, étant le chemin (en arrête) que l'agent à déterminé.

## Solution trouvé
L'agent ayant besoin de noeud en input, il a fallut étudier les différentes manières de sélectionner les noeuds de départ et d'arriver parmis les quatres réunion par la sélection de deux arrêtes.

Pour se faire, nous avons créé une simulation choisissant chacune de ses possibilités et comparant les résultats des réponses de l'agent en conséquence.
Il s'est avéré que choisir les noeuds les plus proches l'un de l'autre offrait les meilleurs résultats. La distance semblant être un facteur déterminant puisque les résultats était proportionnellement mauvais avec la distance entre les noeuds de départ et d'arrivée
