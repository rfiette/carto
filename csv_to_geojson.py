"""
csv_to_geojson.py
-----------------
Convertit l'export CSV de la cartothèque FFCO en fichiers GeoJSON
prêts pour la carte web (un fichier par département + obsoletes.geojson).

Usage :
    python csv_to_geojson.py                         # cherche cartothèque.csv dans le dossier courant
    python csv_to_geojson.py mon_export.csv          # fichier spécifique
    python csv_to_geojson.py --output web/data       # dossier de sortie personnalisé
"""

import csv
import json
import os
import re
import sys
import argparse
from collections import defaultdict

# ── Dossier de sortie par défaut ──
DEFAULT_OUTPUT = "web/data"

# ── Précision des coordonnées (4 décimales = ~11m, largement suffisant) ──
PRECISION = 4


def parse_wkt_polygon(wkt):
    """
    Convertit un WKT POLYGON en liste de coordonnées GeoJSON.
    Ex: "POLYGON ((lng lat, lng lat, ...))" → [[lng, lat], ...]
    """
    if not wkt or not wkt.strip():
        return None

    # Extraire les coordonnées entre les parenthèses
    m = re.search(r'POLYGON\s*\(\((.+)\)\)', wkt.strip(), re.IGNORECASE)
    if not m:
        return None

    coords_str = m.group(1)
    coords = []
    for pair in coords_str.split(','):
        parts = pair.strip().split()
        if len(parts) >= 2:
            try:
                lng = round(float(parts[0]), PRECISION)
                lat = round(float(parts[1]), PRECISION)
                coords.append([lng, lat])
            except ValueError:
                continue

    return coords if len(coords) >= 3 else None


def nettoyer_echelle(echelle):
    """Normalise l'échelle : ' 1/7500' → '1/7500'"""
    return echelle.strip() if echelle else ""


def construire_feature(row):
    """Construit une Feature GeoJSON depuis une ligne du CSV."""

    # Polygone
    coords = parse_wkt_polygon(row.get('Contour', ''))
    geometry = None
    if coords:
        geometry = {
            "type": "Polygon",
            "coordinates": [coords]
        }

    # Département
    dept = (row.get('Département') or row.get('D\xe9partement') or '').strip().zfill(2)

    # Statut obsolète
    obsolete_val = (row.get('Obsolète') or row.get('Obsol\xe8te') or '').strip()
    obsolete = obsolete_val.lower() in ('oui', 'true', '1', 'yes')

    # Numéro FFCO → id_ffco (on extrait la partie numérique)
    numero = row.get('Numéro') or row.get('Num\xe9ro') or ''
    numero = numero.strip()

    # URL fiche FFCO (construite depuis le numéro si pas fournie)
    url_champ = (row.get('URL') or '').strip()

    props = {
        "id_ffco":       numero,                                          # ex: "2024-D13-0042"
        "nom":           (row.get('Nom') or '').strip(),
        "_dept":         dept,
        "numero":        numero,
        "commune":       (row.get('Commune') or '').strip(),
        "echelle":       nettoyer_echelle(row.get('Échelle') or row.get('\xc9chelle') or ''),
        "surface":       (row.get('Surface') or '').strip().replace(',', '.') + ' km²',
        "format":        (row.get('Format') or '').strip(),
        "annee":         (row.get('Année') or row.get('Ann\xe9e') or '').strip(),
        "cartographes":  (row.get('Cartographes') or '').strip(),
        "proprietaire":  (row.get('Propriétaire') or row.get('Propri\xe9taire') or '').strip(),
        "niveau":        (row.get('Niveau') or '').strip(),
        "specialite":    (row.get('Spécialité') or row.get('Sp\xe9cialit\xe9') or '').strip(),
        "contacts":      (row.get('Contacts') or '').strip(),
        "latitude":      (row.get('Latitude') or '').strip(),
        "longitude":     (row.get('Longitude') or '').strip(),
        "date_saisie":   (row.get('Date saisie') or '').strip(),
        "date_depot":    (row.get('Date dépôt') or row.get('Date d\xe9p\xf4t') or '').strip(),
        "valide":        (row.get('Validée') or row.get('Valid\xe9e') or '').strip(),
        "ppo":           (row.get('PPO') or '').strip(),
        "observations":  (row.get('Observations') or '').strip(),
        "type_carte":    (row.get('Type') or '').strip(),
        "base":          (row.get('Base') or '').strip(),
        "fond":          (row.get('Fond') or '').strip(),
        "ref_ign":       (row.get('Ref  IGN') or row.get('Ref IGN') or '').strip(),
        "url":           url_champ,
        "obsolete":      obsolete,
    }

    # Nettoyer les valeurs vides
    props = {k: v for k, v in props.items() if v not in ('', None, ' km²')}
    props['obsolete'] = obsolete  # toujours présent

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": props
    }


def lire_csv(filepath):
    """Lit le CSV FFCO (encodage latin-1, séparateur ;)."""
    features = []
    erreurs = 0

    # Détecter l'encodage
    for encoding in ['latin-1', 'utf-8-sig', 'utf-8', 'cp1252']:
        try:
            with open(filepath, 'r', encoding=encoding, newline='') as f:
                # Test lecture
                f.read(100)
            print(f"  Encodage détecté : {encoding}")
            break
        except UnicodeDecodeError:
            continue
    else:
        encoding = 'latin-1'

    with open(filepath, 'r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, delimiter=';', quotechar='"')
        for i, row in enumerate(reader, 1):
            try:
                feat = construire_feature(row)
                features.append(feat)
            except Exception as e:
                erreurs += 1
                if erreurs <= 5:
                    print(f"  ⚠ Ligne {i+1} ignorée : {e}")

    print(f"  {len(features)} cartes lues, {erreurs} erreurs")
    return features


def sauvegarder_geojson(filepath, features):
    """Sauvegarde un GeoJSON compact."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(filepath) // 1024
    return size_kb


def main():
    parser = argparse.ArgumentParser(description='Convertit le CSV FFCO en GeoJSON')
    parser.add_argument('csv', nargs='?', default=None, help='Fichier CSV (défaut: cartothèque.csv)')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT, help=f'Dossier de sortie (défaut: {DEFAULT_OUTPUT})')
    parser.add_argument('--no-split', action='store_true', help='Ne pas séparer par département (un seul fichier)')
    args = parser.parse_args()

    # Trouver le fichier CSV
    if args.csv:
        csv_path = args.csv
    else:
        # Chercher automatiquement
        candidates = [
            'cartothèque.csv', 'cartotheque.csv',
            'cartothèque.CSV', 'cartotheque.CSV',
        ]
        csv_path = None
        for c in candidates:
            if os.path.exists(c):
                csv_path = c
                break
        if not csv_path:
            # Chercher n'importe quel CSV dans le dossier courant
            csvs = [f for f in os.listdir('.') if f.lower().endswith('.csv')]
            if csvs:
                csv_path = csvs[0]
                print(f"  CSV trouvé automatiquement : {csv_path}")
            else:
                print("ERREUR : aucun fichier CSV trouvé.")
                print("Usage : python csv_to_geojson.py cartothèque.csv")
                sys.exit(1)

    print(f"\nLecture du CSV : {csv_path}")
    features = lire_csv(csv_path)

    if not features:
        print("Aucune carte lue. Vérifier le fichier.")
        sys.exit(1)

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    if args.no_split:
        # Un seul fichier
        out = os.path.join(output_dir, 'cartes_france.geojson')
        size = sauvegarder_geojson(out, features)
        avec_poly = sum(1 for f in features if f['geometry'])
        print(f"\n  {out} : {len(features)} cartes ({avec_poly} avec polygone) — {size} Ko")
    else:
        # Séparer par département + actives/obsolètes
        print(f"\nGénération des fichiers dans : {output_dir}/")

        actifs_par_dept  = defaultdict(list)
        obsoletes        = []
        sans_polygone    = 0

        for feat in features:
            dept = feat['properties'].get('_dept', '??')
            obs  = feat['properties'].get('obsolete', False)
            if feat['geometry'] is None:
                sans_polygone += 1

            if obs:
                obsoletes.append(feat)
            else:
                actifs_par_dept[dept].append(feat)

        # Fichiers par département (actifs)
        total_actifs = 0
        for dept in sorted(actifs_par_dept.keys()):
            feats = actifs_par_dept[dept]
            out = os.path.join(output_dir, f'{dept}.geojson')
            size = sauvegarder_geojson(out, feats)
            avec = sum(1 for f in feats if f['geometry'])
            print(f"  {dept}.geojson : {len(feats)} cartes ({avec} avec polygone) — {size} Ko")
            total_actifs += len(feats)

        # Fichier obsolètes (tous départements)
        out_obs = os.path.join(output_dir, 'obsoletes.geojson')
        size_obs = sauvegarder_geojson(out_obs, obsoletes)
        avec_obs = sum(1 for f in obsoletes if f['geometry'])
        print(f"\n  obsoletes.geojson : {len(obsoletes)} cartes ({avec_obs} avec polygone) — {size_obs} Ko")

        print(f"\n{'='*50}")
        print(f"TERMINÉ")
        print(f"  Actives          : {total_actifs}")
        print(f"  Obsolètes        : {len(obsoletes)}")
        print(f"  Sans polygone    : {sans_polygone}")
        print(f"  Total            : {len(features)}")
        print(f"  Dossier          : {os.path.abspath(output_dir)}")
        print(f"\nMaintenant tu peux lancer le serveur :")
        print(f"  cd web && python -m http.server 8000")


if __name__ == '__main__':
    main()
