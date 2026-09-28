#!/usr/bin/env python3
"""Validate the eight deliverable tables and the Django fixture."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FILES={
 'ingredients':'processed/ingredients.csv',
 'ingredient_prices':'processed/ingredient_prices.csv',
 'ingredient_shelf_life':'processed/ingredient_shelf_life.csv',
 'recipes':'processed/recipes.csv',
 'recipe_ingredients':'processed/recipe_ingredients.csv',
 'recipe_tags':'processed/recipe_tags.csv',
 'ingredient_aliases':'mapping/ingredient_aliases.csv',
 'unit_conversions':'mapping/unit_conversions.csv',
}
KEYS={
 'ingredients':'ingredient_code','ingredient_prices':'price_code',
 'ingredient_shelf_life':'shelf_life_code','recipes':'recipe_code',
 'recipe_ingredients':'recipe_ingredient_code','recipe_tags':'recipe_tag_code',
 'ingredient_aliases':'alias_code','unit_conversions':'conversion_code',
}
tables={}
for name,rel in FILES.items():
    with open(ROOT/rel,newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)>=80,(name,'kurang dari 80 baris',len(rows))
    key=KEYS[name]
    assert len({r[key] for r in rows})==len(rows),(name,'primary key ganda')
    tables[name]=rows

ingredient={r['ingredient_code']:r for r in tables['ingredients']}
recipe={r['recipe_code']:r for r in tables['recipes']}
for name in ('ingredient_prices','ingredient_shelf_life','recipe_ingredients','ingredient_aliases','unit_conversions'):
    for row in tables[name]:
        assert row['ingredient_code'] in ingredient,(name,row)
for name in ('recipe_ingredients','recipe_tags'):
    for row in tables[name]:
        assert row['recipe_code'] in recipe,(name,row)
for row in tables['ingredient_prices']:
    assert float(row['price_rupiah'])>0 and float(row['quantity'])>0
    assert row['region'] and row['recorded_at'] and row['source_url']
    assert row['source_recorded_at'] and row['source_license']
for row in tables['ingredient_shelf_life']:
    assert 0<int(row['min_days'])<=int(row['max_days'])
    assert 0<int(row['warning_days'])<=int(row['min_days'])
    assert row['source_url'] and row['source_license']
    assert row['shelf_life_status']=='referensi_perlu_verifikasi_lokal'
for row in tables['unit_conversions']:
    if row['conversion_status']=='unusable':
        assert not row['gram_equivalent']
    else:
        assert float(row['gram_equivalent'])>0

prices=defaultdict(list)
for p in tables['ingredient_prices']:
    prices[p['ingredient_code']].append(p)
links=defaultdict(list)
for r in tables['recipe_ingredients']:
    links[r['recipe_code']].append(r)
tags=defaultdict(set)
for r in tables['recipe_tags']:
    tags[r['recipe_code']].add(r['tag'])
ready=[r for r in tables['recipes'] if r['is_plannable']=='true']
assert len(ready)>=15
for r in ready:
    assert int(r['base_servings'])>0 and r['meal_type'] in ('sarapan','makan_siang','makan_malam')
    assert r['instructions'] and not r['missing_data_reason']
    assert links[r['recipe_code']] and 'halal' in tags[r['recipe_code']]
    for x in links[r['recipe_code']]:
        assert x['unit']=='g' and float(x['quantity'])>0
        assert x['quantity_status']=='curated'
        assert ingredient[x['ingredient_code']]['calories_per_100g']
        assert any(p['region']=='Kabupaten Garut' and p['unit']=='kg' and p['recorded_at']=='2026-09-28' for p in prices[x['ingredient_code']])

fixture=json.loads((ROOT/'fixtures/catalog_seed.json').read_text(encoding='utf-8'))
assert len(fixture)==sum(map(len,tables.values()))
assert len({(x['model'],x['pk']) for x in fixture})==len(fixture)
for x in fixture:
    assert x['model'].startswith('catalog.') and isinstance(x['fields'],dict)

print('VALID:')
for name,rows in tables.items():print(f'  {name}: {len(rows)} baris')
print(f'  resep siap dihitung: {len(ready)}')
print(f'  fixture Django: {len(fixture)} objek')
