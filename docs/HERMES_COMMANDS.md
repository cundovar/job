# Hermes commands

Ces commandes sont prevues pour etre appelees par Hermes depuis la racine du projet.

## Lire les meilleures offres

```bash
python3 -m hermes_commands.job_top
python3 -m hermes_commands.job_top --limit 10
```

Lit `data/jobs_cache.json`, classe les offres par score et affiche un resume court avec le CV conseille.

## Lancer la recherche du jour

```bash
python3 -m hermes_commands.job_today
```

Lance le pipeline complet sans email ni Google Sheets par defaut. Pour autoriser les sorties externes :

```bash
python3 -m hermes_commands.job_today --send-outputs
```

## Preparer une candidature

```bash
python3 -m hermes_commands.job_prepare 1
```

Prepare la candidature pour l'offre numero 1 du classement :

- resume de l'offre
- CV recommande
- lettre de motivation
- mail de candidature
- metadata JSON

Les fichiers sont crees dans `output/applications/`.

## Marquer comme postule

```bash
python3 -m hermes_commands.job_apply 1
```

Marque l'offre numero 1 comme postulee dans `data/applications_tracker.json`.

Options utiles :

```bash
python3 -m hermes_commands.job_apply 1 --follow-up-days 10
python3 -m hermes_commands.job_apply 1 --notes "Candidature envoyee via formulaire"
```

## Voir les relances

```bash
python3 -m hermes_commands.job_relance
```

Liste les candidatures dont la date de relance est arrivee.

## Voir le statut global

```bash
python3 -m hermes_commands.job_status
```

Affiche :

- nombre d'offres en cache
- repartition POSTULER / PEUT-ETRE / PASSER
- candidatures pretes
- candidatures envoyees
- relances a faire

## Fichiers generes

Les fichiers runtime sont ignores par Git :

```text
data/
output/
```

## Sources d'offres

Les sources sont configurees dans `config/sources.yaml`.

Par defaut, seules les sources historiques sont actives :

```text
France Travail
Adzuna
Emploi Territorial
```

Les sources optionnelles sont desactivees par defaut :

```text
Jooble
Remote OK
```

Jooble necessite `JOOBLE_API_KEY`.
