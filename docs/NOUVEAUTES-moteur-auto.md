# 🤖 Ce qui a changé : le hub a maintenant un "robot chercheur de bonnes affaires"

_Petit récap pour l'équipe — version sans jargon._

## En une phrase

Jusqu'ici, il fallait lancer un scrape **à la main** quand on voulait checker Leboncoin.
Maintenant, le PC fixe peut faire tourner un **robot autonome** qui surveille Leboncoin
**tout seul, en boucle**, et remonte les annonces dans notre base partagée — sans que
personne ait à cliquer.

## Avant → Après

| Avant | Après |
|---|---|
| Je lance un scrape manuellement | Un moteur tourne en fond et scrape en boucle |
| Je dois être devant le PC | Le PC bosse tout seul (objectif : 24/7) |
| Les résultats arrivent quand je m'en occupe | Les nouvelles annonces remontent en continu |

## Concrètement, le robot sait :

- 🔁 **Surveiller plusieurs recherches** en boucle (ex. "PC portable", "PS5"…) et les
  répartir, même si deux d'entre nous suivent la même recherche (il ne la scrape qu'une fois).
- 🆕 **Repérer uniquement le neuf** : il se souvient de ce qu'il a déjà vu, donc pas de doublons.
- 💸 **Détecter les baisses de prix** sur une annonce déjà repérée.
- 🧹 **Filtrer le bruit tout seul** (prix à 0, au-dessus du budget, mots interdits type
  "pour pièces / HS / cassé").
- 💾 **Tout écrire dans notre base Supabase partagée**, à dispo pour le groupe.
- 🛟 **Résister aux coupures** : si internet saute, il met les trouvailles de côté en local
  et les renvoie dès que ça revient. Rien n'est perdu.

## Ce que ça change **pour toi** tout de suite

Honnêtement : **rien de visible dans l'interface pour l'instant** 🙂.
Cette étape, c'était de **construire le moteur** (la partie invisible, le plus gros du boulot).
Les annonces sont collectées et stockées, mais on n'a pas encore l'écran joli pour les
parcourir, ni les alertes.

## Ce qui arrive ensuite

- 🧠 **Une IA qui note chaque annonce** : score de revente, prix du marché estimé, marge en €,
  prix max conseillé à l'achat. → fini de trier à la main, le robot dira "celle-là vaut le coup".
- 📱 **Des alertes Telegram** sur ton téléphone quand une **grosse affaire** sort (tu pourras
  réagir direct, même loin du PC).
- 🖥️ **Un onglet "Opportunités"** dans le hub pour tout voir joliment, filtrer, et se coordonner
  ("je m'en occupe", etc.).

## Petit point honnêteté

- Le robot scrape Leboncoin, donc parfois LBC affiche un **captcha** : il faut le résoudre une
  fois à la main dans la fenêtre, puis ça repart.
- Pour l'instant, **un seul PC** (le fixe de Tristan) fait tout le travail.
- C'est **100 % gratuit** : pas d'abonnement payant ajouté.

---

_TL;DR : on a posé les **fondations d'un détecteur d'affaires automatique**. Le moteur tourne
et collecte déjà. Les parties "IA qui note" + "alertes téléphone" + "bel écran" arrivent dans
les prochaines étapes._
