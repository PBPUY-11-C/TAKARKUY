"""Seeded planner over the curated local recipe and price catalog."""

import json
from collections import Counter, defaultdict
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from heapq import nsmallest
from itertools import combinations_with_replacement, product
from math import ceil
from random import Random

from apps.catalog.content_policy import protect_plan_instructions
from apps.catalog.models import Ingredient, IngredientPrice, Recipe

from .protein_groups import main_protein_group
from .purchase_units import load_fruit_rules, whole_fruit_quote

REGION = "Kabupaten Garut"
MEALS = ("sarapan", "makan_siang", "makan_malam")
MEAL_LABELS = {"sarapan": "Pagi", "makan_siang": "Siang", "makan_malam": "Malam"}
TARGET_TAGS = {
    "seimbang": "seimbang_internal",
    "tinggi_protein": "tinggi_protein",
    "rendah_kalori": "rendah_kalori",
}
NUTRIENTS = ("calories", "protein", "carbs", "fat")
MAX_TIE_BREAK_CHECKS = 300000
NUTRITION_BEAM_WIDTH = 5
HALAL_TAG = "halal"
# Search runs on at most this many recipes per meal, spread across the price
# range, so response time stays flat as the catalog grows.
CANDIDATE_POOL_SIZE = 40
# The budget is the ceiling; each generate picks its spend at random from 60%
# of the budget up to the priciest affordable plan, so menus vary without
# collapsing to the cheapest recipes. A single menu may cost at most twice the
# average share of one meal slot, so a small budget never gets one luxury dish.
SPEND_FLOOR_RATIO = Decimal("0.60")
MEAL_COST_CAP_MULTIPLIER = 2
# When the catalog cannot reach 60% of a large budget, vary within this share
# below the priciest plan instead.
CATALOG_VARIETY_SHARE = 0.10
# Day bundles whose cost is within this share of the daily target count as
# equally close, so protein variety and the seeded tie-break decide.
NUTRITION_COST_BAND_RATIO = 0.10
MIN_NUTRITION_COST_BAND = 2500
SCORE_LENGTH = 7  # elements in a _recipe_patterns score
HIGH_PROTEIN_GRAMS_PER_DAY = Decimal("80")
CALORIE_LIMITS_BY_MEAL = {
    "sarapan": Decimal("500"),
    "makan_siang": Decimal("325"),
    "makan_malam": Decimal("325"),
}
# Many lunch/dinner recipes are side dishes (lauk) eaten with rice. When rice is
# on, a lauk without any carbohydrate ingredient gets one plate of rice per
# serving, priced and counted like any other ingredient.
RICE_CODE = "ING-BERAS-MEDIUM"
RICE_GRAMS_PER_SERVING = 80  # raw rice, about one plate of cooked rice
RICE_MEALS = ("makan_siang", "makan_malam")
# Recipes using pantry stock that expires soon are guaranteed a place in the
# search pool, up to this many per meal.
PANTRY_POOL_SLOTS = 8


def rice_included(rice, servings, targets):
    """'auto' adds rice for 1-2 people, except under a low-calorie target."""
    if rice == "yes":
        return True
    return rice == "auto" and servings <= 2 and "rendah_kalori" not in targets


class RiceLink:
    """A recipe-ingredient row for the added rice; never stored in the catalog."""

    unit = "g"
    quantity_status = "curated"
    raw_text = ""
    is_optional = False

    def __init__(self, recipe, ingredient):
        self.recipe_ingredient_code = f"NASI-{recipe.pk}"
        self.ingredient = ingredient
        self.ingredient_id = ingredient.pk
        # Scaled by servings / base_servings like catalog rows.
        self.quantity = RICE_GRAMS_PER_SERVING * recipe.base_servings


def needs_rice(meal_type, ingredients):
    return meal_type in RICE_MEALS and not any(
        link.ingredient.category == "karbohidrat" for link in ingredients
    )


def purchase_grams(link):
    """Price whole chicken by gross mass without counting bones as eaten protein."""
    edible = Decimal(str(link.quantity))
    if link.quantity_status != "estimated":
        return edible
    try:
        audit = json.loads(link.raw_text)
    except (ValueError, TypeError):
        return edible
    if (
        not isinstance(audit, list)
        or not audit
        or not all(
            isinstance(row, dict) and row.get("purchase_quantity_g") not in ("", None)
            for row in audit
        )
    ):
        return edible
    try:
        gross = sum((Decimal(str(row["purchase_quantity_g"])) for row in audit), Decimal(0))
        source_edible = sum((Decimal(str(row["quantity_g"])) for row in audit), Decimal(0))
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise ValueError("Estimasi massa beli bahan tidak valid.") from exc
    if (
        not gross.is_finite()
        or not source_edible.is_finite()
        or source_edible <= 0
        or gross < source_edible
    ):
        raise ValueError("Estimasi massa beli bahan tidak valid.")
    return edible * gross / source_edible


def money(value):
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_up_price(value, multiple):
    """Round a rupiah estimate up to the next Rp100 or Rp500."""
    return int(
        (Decimal(value) / Decimal(multiple)).to_integral_value(rounding=ROUND_CEILING) * multiple
    )


def _recipe_patterns(candidates, slots, preferred_tags, recent_codes, prior_slot_codes=()):
    """Find each reachable meal cost without enumerating recipe combinations."""
    max_uses = max(1, ceil(slots / len(candidates)))
    patterns_by_cost = {}
    if len(candidates) >= slots:
        # The cost of each ingredient is rounded to Rp100, so many different
        # recipe sets have the same total. Keep the best set for each count/cost.
        # Each candidate enters once, which also prevents repeat menus.
        states = [{} for _ in range(slots + 1)]
        states[0][0] = (
            (),
            0,
            0,
            0,
            0,
            0,
            0,
        )  # indexes, all-target hits, total hits, recent hits, prior hits, protein repeats,
        # pantry hits
        prior_codes = set(prior_slot_codes)

        def rank(state):
            return (-state[4], state[1], -state[5], state[2], state[6], -state[3])

        for index, item in enumerate(candidates):
            code = item["recipe"].pk
            group = item["protein_group"]
            for count in range(min(slots, index + 1), 0, -1):
                for cost, (
                    indexes,
                    all_hits,
                    target_hits,
                    recent_hits,
                    prior_hits,
                    protein_repeats,
                    pantry_hits,
                ) in states[count - 1].items():
                    new_cost = cost + item["cost"]
                    matched = len(preferred_tags & item["tags"])
                    candidate = (
                        (*indexes, index),
                        all_hits + (matched == len(preferred_tags)),
                        target_hits + matched,
                        recent_hits + (code in recent_codes),
                        prior_hits + (code in prior_codes),
                        protein_repeats
                        + sum(candidates[i]["protein_group"] == group for i in indexes),
                        pantry_hits + item.get("pantry_hits", 0),
                    )
                    old = states[count].get(new_cost)
                    if old is None or rank(candidate) > rank(old):
                        states[count][new_cost] = candidate
        patterns = (
            tuple(candidates[index] for index in state[0]) for state in states[slots].values()
        )
    else:
        patterns = combinations_with_replacement(candidates, slots)
    for pattern in patterns:
        counts = Counter(item["recipe"].pk for item in pattern)
        if max(counts.values()) > max_uses:
            continue
        if slots > len(candidates) and len(counts) != len(candidates):
            continue
        cost = sum(item["cost"] for item in pattern)
        recipe_counts = Counter(item["recipe"].pk for item in pattern)
        group_counts = Counter(item["protein_group"] for item in pattern)
        spread = _spread(pattern, recent_codes, prior_slot_codes)
        pattern_score = (
            -sum(
                1
                for index, item in enumerate(spread)
                if index < len(prior_slot_codes) and prior_slot_codes[index] == item["recipe"].pk
            ),
            sum(preferred_tags <= item["tags"] for item in pattern),
            -sum(count - 1 for count in group_counts.values()),
            sum(len(preferred_tags & item["tags"]) for item in pattern),
            sum(item.get("pantry_hits", 0) for item in pattern),
            -sum(1 for item in pattern if item["recipe"].pk in recent_codes),
            len(recipe_counts),
        )
        current = patterns_by_cost.get(cost)
        if current is None or pattern_score > current["score"]:
            patterns_by_cost[cost] = {"items": pattern, "score": pattern_score}
    return patterns_by_cost


def _spread(pattern, recent_codes, prior_slot_codes=()):
    """Arrange a chosen multiset so repeats are separated when possible."""
    counts = Counter(item["recipe"].pk for item in pattern)
    by_code = {item["recipe"].pk: item for item in pattern}
    order = sorted(counts, key=lambda code: (code in recent_codes, by_code[code]["cost"], code))
    result = []
    for day in range(sum(counts.values())):
        old_code = prior_slot_codes[day] if day < len(prior_slot_codes) else None
        available = [code for code in order if counts[code]]
        selected = min(
            available,
            key=lambda code: (
                code == old_code,
                code in recent_codes,
                by_code[code]["cost"],
                code,
            ),
        )
        result.append(by_code[selected])
        counts[selected] -= 1
    return result


def spend_floor(budget):
    """Lowest total a plan aims for: 60% of the budget, rounded down to Rp100."""
    return int(Decimal(budget) * SPEND_FLOOR_RATIO) // 100 * 100


def meal_cost_cap(budget, days, meal_count):
    """Most one menu may cost: twice the budget's average share per meal slot."""
    return int(Decimal(budget) * MEAL_COST_CAP_MULTIPLIER / (days * meal_count))


def daily_limits(targets, meals):
    """Per-person daily protein floor and calorie cap for the chosen meals."""
    protein_floor = (
        (HIGH_PROTEIN_GRAMS_PER_DAY * len(meals) / Decimal(len(MEALS))).quantize(
            Decimal("1"), rounding=ROUND_CEILING
        )
        if "tinggi_protein" in targets
        else None
    )
    calorie_cap = (
        sum((CALORIE_LIMITS_BY_MEAL[meal] for meal in meals), Decimal(0))
        if "rendah_kalori" in targets
        else None
    )
    return protein_floor, calorie_cap


def _target_fit(items, targets):
    """Score 0..1 per recipe for how well it suits the chosen nutrition targets."""
    if not items:
        return {}
    keys = []
    if "tinggi_protein" in targets:
        keys.append(lambda item: -item["nutrition"]["protein"])
    if "rendah_kalori" in targets:
        keys.append(lambda item: item["nutrition"]["calories"])
    if not keys:
        return {id(item): 1.0 if TARGET_TAGS["seimbang"] in item["tags"] else 0.5 for item in items}
    fit = {id(item): 0.0 for item in items}
    for key in keys:
        for position, item in enumerate(sorted(items, key=key)):
            fit[id(item)] += 1 - position / len(items)
    return {code: value / len(keys) for code, value in fit.items()}


def _candidate_pool(items, size, days, rng, recent_codes, targets):
    """Pick a varied, price-spread subset of recipes for one meal.

    The cheapest recipes always stay so a tight budget remains reachable. The
    rest are split into equal price ranges and one recipe is drawn from each,
    favouring target fit and penalising recent menus and repeated proteins.
    """
    if len(items) <= size:
        pool = list(items)
        rng.shuffle(pool)
        return pool
    ordered = sorted(items, key=lambda item: (item["cost"], item["recipe"].pk))
    pool = ordered[: min(days, size)]
    rest = ordered[len(pool) :]
    pantry = sorted(
        (item for item in rest if item.get("pantry_hits", 0)),
        key=lambda item: (-item.get("pantry_hits", 0), item["cost"], item["recipe"].pk),
    )[: min(PANTRY_POOL_SLOTS, size - len(pool))]
    if pantry:
        pool += pantry
        rest = [item for item in rest if not any(item is chosen for chosen in pantry)]
    fit = _target_fit(rest, targets)
    groups = Counter(item["protein_group"] for item in pool)
    buckets = size - len(pool)
    for bucket in range(buckets):
        options = rest[bucket * len(rest) // buckets : (bucket + 1) * len(rest) // buckets]
        if not options:
            continue
        weights = [
            (0.3 + fit[id(item)])
            * (0.25 if item["recipe"].pk in recent_codes else 1)
            / (1 + groups[item["protein_group"]])
            for item in options
        ]
        chosen = rng.choices(options, weights)[0]
        groups[chosen["protein_group"]] += 1
        pool.append(chosen)
    rng.shuffle(pool)
    return pool


def _balance_days(chosen_by_meal, meals, prior_slot_recipes):
    """Reorder each meal's recipes so one day rarely repeats a protein.

    Only the day order changes, so cost and the shopping list stay the same.
    Use this only where nutrition limits do not apply per day.
    """
    if len(meals) < 2:
        return chosen_by_meal
    days = len(chosen_by_meal[meals[0]])

    def penalty():
        score = 0
        for day in range(days):
            day_groups = Counter(chosen_by_meal[meal][day]["protein_group"] for meal in meals)
            score += 2 * sum(count - 1 for count in day_groups.values())
            for meal in meals:
                item = chosen_by_meal[meal][day]
                prior = prior_slot_recipes.get(meal, ())
                if day < len(prior) and prior[day] == item["recipe"].pk:
                    score += 3
                if day and chosen_by_meal[meal][day - 1]["recipe"].pk == item["recipe"].pk:
                    score += 2
        return score

    best = penalty()
    for _ in range(4):
        improved = False
        for meal in meals:
            order = chosen_by_meal[meal]
            for first in range(days):
                for second in range(first + 1, days):
                    order[first], order[second] = order[second], order[first]
                    score = penalty()
                    if score < best:
                        best, improved = score, True
                    else:
                        order[first], order[second] = order[second], order[first]
        if not improved:
            break
    return chosen_by_meal


def _best_patterns_for_total(meals, meal_patterns, total):
    """Choose the best meal mixes for an already reachable total cost."""
    groups = [meal_patterns[meal] for meal in meals]
    if len(groups) == 1:
        return {meals[0]: groups[0][total]["items"]}
    if total == sum(max(group) for group in groups):
        return {meal: group[max(group)]["items"] for meal, group in zip(meals, groups)}
    if total == sum(min(group) for group in groups):
        return {meal: group[min(group)]["items"] for meal, group in zip(meals, groups)}

    best_rank = None
    best_choice = None
    if len(groups) == 2:
        for first_cost, first in groups[0].items():
            second = groups[1].get(total - first_cost)
            if second is None:
                continue
            rank = tuple(first["score"][i] + second["score"][i] for i in range(SCORE_LENGTH))
            if best_rank is None or rank > best_rank:
                best_rank, best_choice = rank, (first, second)
    else:
        last_group = groups[2]
        upper_rank = tuple(
            sum(max(pattern["score"][i] for pattern in group.values()) for group in groups)
            for i in range(SCORE_LENGTH)
        )
        checks = 0
        first_match_at = None
        for first_cost, first in groups[0].items():
            remaining = total - first_cost
            for second_cost, second in groups[1].items():
                checks += 1
                if first_match_at is not None and checks - first_match_at > MAX_TIE_BREAK_CHECKS:
                    return {meal: choice["items"] for meal, choice in zip(meals, best_choice)}
                third = last_group.get(remaining - second_cost)
                if third is None:
                    continue
                if first_match_at is None:
                    first_match_at = checks
                rank = tuple(
                    first["score"][i] + second["score"][i] + third["score"][i]
                    for i in range(SCORE_LENGTH)
                )
                if best_rank is None or rank > best_rank:
                    best_rank, best_choice = rank, (first, second, third)
                    if rank == upper_rank:
                        return {meal: choice["items"] for meal, choice in zip(meals, best_choice)}
    return {meal: choice["items"] for meal, choice in zip(meals, best_choice)}


def _nutrition_plan(
    candidates,
    meals,
    days,
    servings,
    targets,
    budget_limit,
    recent_codes,
    prior_slot_recipes,
    rng,
):
    """Choose affordable day bundles; nutritional limits apply to each whole day."""
    protein_floor, calorie_cap = daily_limits(targets, meals)
    per_person = {
        id(item): (
            item["nutrition"]["protein"] / Decimal(servings),
            item["nutrition"]["calories"] / Decimal(servings),
        )
        for meal in meals
        for item in candidates[meal]
    }
    bundles = []  # cost, items, protein repeats within the day, protein groups, tie-break
    for items in product(*(candidates[meal] for meal in meals)):
        protein = sum((per_person[id(item)][0] for item in items), Decimal(0))
        calories = sum((per_person[id(item)][1] for item in items), Decimal(0))
        if protein_floor is not None and protein < protein_floor:
            continue
        if calorie_cap is not None and calories > calorie_cap:
            continue
        groups = tuple(item["protein_group"] for item in items)
        bundles.append(
            (
                sum(item["cost"] for item in items),
                items,
                len(groups) - len(set(groups)),
                groups,
                rng.random(),
            )
        )
    if not bundles:
        conditions = []
        if protein_floor is not None:
            conditions.append(f"minimal {money(protein_floor)} g protein")
        if calorie_cap is not None:
            conditions.append(f"maksimal {money(calorie_cap)} kkal")
        raise ValueError(
            "Belum ada kombinasi menu yang memenuhi "
            + " dan ".join(conditions)
            + " per orang untuk waktu makan yang dipilih. Coba tambah variasi resep atau ubah pilihan waktu makan/pantangan."
        )

    bundles.sort(key=lambda bundle: bundle[0])
    eligible_codes = {
        meal: {bundle[1][index]["recipe"].pk for bundle in bundles}
        for index, meal in enumerate(meals)
    }
    repeat_caps = {meal: max(1, ceil(days / len(eligible_codes[meal]))) for meal in meals}
    min_daily_cost = bundles[0][0]
    max_daily_cost = bundles[-1][0]
    if round_up_price(min_daily_cost * days, 500) > budget_limit:
        raise ValueError(
            f"Budget belum cukup untuk target gizi ini. Perkiraan batas bawah biaya "
            f"{days} hari adalah Rp {round_up_price(min_daily_cost * days, 500):,}.".replace(
                ",", "."
            )
        )
    daily_ceiling = min(max_daily_cost, budget_limit / days)
    daily_floor = max(min_daily_cost, spend_floor(budget_limit) / days)
    if daily_floor > daily_ceiling:
        daily_floor = daily_ceiling * (1 - CATALOG_VARIETY_SHARE)
    daily_target = rng.uniform(daily_floor, daily_ceiling)

    # A small beam preserves affordable alternatives when a high-cost choice
    # would consume the budget or repeat a recipe needed on later days.
    states = [(0, (), Counter())]
    for day in range(days):
        next_states = []
        remaining_days = days - day - 1
        for spent, selected, uses in states:
            remaining_budget = budget_limit - spent - remaining_days * min_daily_cost
            target_cost = min(daily_target, (budget_limit - spent) / (remaining_days + 1))
            yesterday = tuple(item["protein_group"] for item in selected[-1]) if selected else ()
            cost_band = max(MIN_NUTRITION_COST_BAND, target_cost * NUTRITION_COST_BAND_RATIO)

            def rank_options(enforce_repeat_cap):
                ranked = []
                for cost, items, day_repeats, groups, tie_break in bundles:
                    if cost > remaining_budget:
                        break
                    if enforce_repeat_cap and any(
                        uses[item["recipe"].pk] >= repeat_caps[meal]
                        for meal, item in zip(meals, items)
                    ):
                        continue
                    codes = tuple(item["recipe"].pk for item in items)
                    prior_hits = sum(
                        day < len(prior_slot_recipes.get(meal, ()))
                        and prior_slot_recipes[meal][day] == code
                        for meal, code in zip(meals, codes)
                    )
                    repeats = sum(uses[code] for code in codes)
                    recent_hits = sum(code in recent_codes for code in codes)
                    pantry_hits = sum(item.get("pantry_hits", 0) for item in items)
                    same_as_yesterday = sum(a == b for a, b in zip(groups, yesterday))
                    # Costs within one band count as equally close to the daily
                    # target, so protein variety and the seeded tie-break decide.
                    rank = (
                        abs(cost - target_cost) // cost_band,
                        day_repeats,
                        repeats,
                        prior_hits,
                        -pantry_hits,
                        recent_hits,
                        same_as_yesterday,
                        tie_break,
                        codes,
                    )
                    ranked.append((rank, cost, items))
                return ranked

            ranked = rank_options(True)
            if not ranked:
                ranked = rank_options(False)
            for _, cost, items in nsmallest(NUTRITION_BEAM_WIDTH, ranked):
                new_uses = uses.copy()
                new_uses.update(item["recipe"].pk for item in items)
                next_states.append((spent + cost, (*selected, items), new_uses))
        if not next_states:
            raise ValueError(
                "Belum ditemukan rencana bervariasi yang memenuhi target gizi dan budget. "
                "Coba tambah budget, kurangi hari, atau longgarkan pantangan bahan."
            )
        next_states.sort(
            key=lambda state: (
                abs(state[0] - daily_target * (day + 1)),
                sum(max(0, count - 1) for count in state[2].values()),
                -state[0],
            )
        )
        states = next_states[:NUTRITION_BEAM_WIDTH]
    spent, selected, _ = min(
        states,
        key=lambda state: (
            sum(max(0, count - 1) for count in state[2].values()),
            abs(state[0] - daily_target * days),
        ),
    )
    return (
        spent,
        {meal: [day_items[index] for day_items in selected] for index, meal in enumerate(meals)},
        protein_floor,
        calorie_cap,
    )


def _load_candidates(
    requested_meals,
    servings,
    exclude_ingredients,
    allergens=(),
    *,
    with_rice=False,
    priority_ingredients=frozenset(),
):
    """Price and nutrition-complete halal recipes per meal for the given servings.

    With rice, a lunch/dinner lauk gets RICE_GRAMS_PER_SERVING of rice per serving
    unless the user avoids rice. priority_ingredients are pantry stock that
    expires soon; each recipe counts how many of them it uses.
    """
    from apps.catalog.allergens import recipe_allowed

    snapshot = (
        IngredientPrice.objects.filter(region=REGION, price_status="published", unit="kg")
        .order_by("-recorded_at")
        .values_list("recorded_at", flat=True)
        .first()
    )
    if snapshot is None:
        raise ValueError("Data harga Kabupaten Garut belum tersedia. Impor katalog lebih dulu.")

    prices, price_records = {}, {}
    for price in IngredientPrice.objects.filter(
        region=REGION, recorded_at=snapshot, price_status="published", unit="kg"
    ):
        prices[price.ingredient_id] = Decimal(price.price_rupiah) / Decimal(str(price.quantity))
        price_records[price.ingredient_id] = price
    # Supplement missing local ingredients only; make mixed provenance visible
    # in the result instead of claiming every quote came from Garut.
    for price in IngredientPrice.objects.filter(
        price_status="retail_reference", unit="kg"
    ).order_by("-recorded_at", "-price_code"):
        if price.ingredient_id not in prices and price.quantity > 0:
            prices[price.ingredient_id] = Decimal(price.price_rupiah) / Decimal(str(price.quantity))
            price_records[price.ingredient_id] = price
    fruit_rules = load_fruit_rules()

    def ingredient_purchase_cost(ingredient_code, edible_grams):
        if ingredient_code in fruit_rules:
            return whole_fruit_quote(
                edible_grams, prices[ingredient_code], fruit_rules[ingredient_code]
            )["cost"]
        return round_up_price(
            Decimal(str(edible_grams)) * prices[ingredient_code] / Decimal("1000"), 100
        )

    rice = None
    if with_rice and RICE_CODE in prices:
        rice = Ingredient.objects.filter(pk=RICE_CODE).first()
        if rice is not None and any(term in rice.name.casefold() for term in exclude_ingredients):
            rice = None
    candidates = defaultdict(list)
    matched_terms, excluded_names = set(), set()
    recipes = Recipe.objects.filter(is_active=True, is_plannable=True).prefetch_related(
        "recipeingredient_set__ingredient", "recipetag_set"
    )
    for recipe in recipes:
        if not recipe.base_servings or recipe.meal_type not in requested_meals:
            continue
        tags = {tag.tag for tag in recipe.recipetag_set.all()}
        if HALAL_TAG not in tags:
            continue
        ingredients = list(recipe.recipeingredient_set.all())
        if not recipe_allowed(recipe, ingredients, allergens):
            continue
        if any(
            term in link.ingredient.name.casefold()
            for link in ingredients
            for term in exclude_ingredients
        ):
            for link in ingredients:
                for term in exclude_ingredients:
                    if term in link.ingredient.name.casefold():
                        matched_terms.add(term)
                        excluded_names.add(link.ingredient.name)
            continue
        if not ingredients or any(
            link.unit != "g"
            or link.quantity is None
            or link.quantity <= 0
            or link.ingredient_id not in prices
            or any(
                getattr(link.ingredient, f"{nutrient}_per_100g") is None for nutrient in NUTRIENTS
            )
            for link in ingredients
        ):
            continue
        added_rice = rice is not None and needs_rice(recipe.meal_type, ingredients)
        if added_rice:
            ingredients = [*ingredients, RiceLink(recipe, rice)]

        scale = Decimal(servings) / Decimal(recipe.base_servings)
        ingredient_costs = {
            link.recipe_ingredient_code: ingredient_purchase_cost(
                link.ingredient_id, purchase_grams(link) * scale
            )
            for link in ingredients
        }
        nutrition = {
            nutrient: sum(
                (
                    Decimal(str(link.quantity))
                    * scale
                    * Decimal(str(getattr(link.ingredient, f"{nutrient}_per_100g")))
                    / Decimal("100")
                    for link in ingredients
                ),
                Decimal("0"),
            )
            for nutrient in NUTRIENTS
        }
        candidates[recipe.meal_type].append(
            {
                "recipe": recipe,
                "tags": tags,
                "ingredients": ingredients,
                "ingredient_costs": ingredient_costs,
                "scale": scale,
                "cost": sum(ingredient_costs.values()),
                "nutrition": nutrition,
                "protein_group": main_protein_group(ingredients),
                "with_rice": added_rice,
                "pantry_hits": len(
                    {link.ingredient_id for link in ingredients} & priority_ingredients
                ),
            }
        )

    return (
        snapshot,
        prices,
        price_records,
        fruit_rules,
        ingredient_purchase_cost,
        candidates,
        matched_terms,
        excluded_names,
    )


def budget_preference_notes(schedule, total, budget):
    """Explain soft preferences without relaxing the mandatory budget ceiling."""
    notes = []
    if total <= budget and total < spend_floor(budget):
        notes.append(
            "Preferensi belanja minimal 60% budget dilonggarkan karena pilihan katalog, "
            "target gizi, atau pembelian gabungan. Sisa budget tetap milikmu."
        )
    count = sum(len(day["meals"]) for day in schedule)
    cap = MEAL_COST_CAP_MULTIPLIER * Decimal(budget) / count if count else Decimal(0)
    if any(meal["cost"] > cap for day in schedule for meal in day["meals"]):
        notes.append(
            "Preferensi biaya per menu maksimal 2× jatah rata-rata dilonggarkan "
            "untuk ketersediaan menu, target gizi, atau penggantian pilihanmu. "
            "Total belanja tetap wajib dalam budget sebelum disimpan."
        )
    return notes


def quote_schedule(schedule, *, servings, targets, catalog):
    """Quote fixed recipe codes without searching or querying the database.

    Both alternatives and previews use this basket calculation. Load the
    catalog once per request, combine fruit needs across every slot, then
    round the final shopping total. Nutrition is checked for every whole day.
    """
    _, prices, price_records, fruit_rules, _, candidates, _, _ = catalog
    meals_available = tuple(meal for meal in MEALS if candidates.get(meal))
    by_code = {
        meal: {item["recipe"].pk: item for item in candidates[meal]} for meal in meals_available
    }
    if not schedule or not meals_available:
        raise ValueError("Susunan menu kosong atau tidak tersedia.")
    protein_floor, calorie_cap = daily_limits(targets, meals_available)
    shopping, output_schedule, selected = {}, [], []
    nutrition_total = {nutrient: Decimal("0") for nutrient in NUTRIENTS}
    for day, slots in enumerate(schedule, start=1):
        if set(slots) != set(meals_available):
            raise ValueError("Ketersediaan waktu makan berubah. Buat pratinjau susunan baru.")
        day_items = []
        for meal in meals_available:
            item = by_code[meal].get(slots[meal])
            if item is None:
                raise ValueError(
                    "Menu tidak tersedia, melanggar pantangan, atau data harga/gizinya belum lengkap."
                )
            day_items.append(item)
        day_nutrition = {
            nutrient: sum((item["nutrition"][nutrient] for item in day_items), Decimal("0"))
            for nutrient in NUTRIENTS
        }
        protein = day_nutrition["protein"] / Decimal(servings)
        calories = day_nutrition["calories"] / Decimal(servings)
        if (protein_floor is not None and protein < protein_floor) or (
            calorie_cap is not None and calories > calorie_cap
        ):
            raise ValueError(
                "Menu pengganti tidak memenuhi target gizi harian bersama menu lainnya. Pilih alternatif lain."
            )
        selected.extend(day_items)
        for nutrient in NUTRIENTS:
            nutrition_total[nutrient] += day_nutrition[nutrient]
        meals = []
        for meal, item in zip(meals_available, day_items):
            for link in item["ingredients"]:
                code = link.ingredient_id
                if code not in shopping:
                    shopping[code] = {
                        "name": link.ingredient.name,
                        "category": "sayur" if code == "ING-KUBIS" else link.ingredient.category,
                        "quantity": Decimal("0"),
                        "cost": 0,
                    }
                shopping[code]["quantity"] += purchase_grams(link) * item["scale"]
                shopping[code]["cost"] += item["ingredient_costs"][link.recipe_ingredient_code]
            meals.append(
                {
                    "instructions": item["recipe"].instructions,
                    "instruction_status": item["recipe"].instruction_status,
                    "instruction_review_note": item["recipe"].instruction_review_note,
                    "instruction_reviewed_on": item["recipe"].instruction_reviewed_on,
                    "servings": servings,
                    "type": meal,
                    "label": MEAL_LABELS[meal],
                    "recipe_code": item["recipe"].pk,
                    "name": item["recipe"].name,
                    "cost": item["cost"],
                    "estimated_quantities": any(
                        link.quantity_status == "estimated" for link in item["ingredients"]
                    ),
                    "calories": money(item["nutrition"]["calories"] / Decimal(servings)),
                    # Only present when true, so snapshots of older plans stay identical.
                    **({"with_rice": True} if item.get("with_rice") else {}),
                }
            )
        output_schedule.append(
            {"number": day, "meals": meals, "protein": money(protein), "calories": money(calories)}
        )
    groups = defaultdict(list)
    for code, item in shopping.items():
        fruit_purchase = None
        if code in fruit_rules:
            fruit_purchase = whole_fruit_quote(item["quantity"], prices[code], fruit_rules[code])
            item["cost"] = fruit_purchase["cost"]
        groups[item["category"]].append(
            {
                "ingredient_code": code,
                "name": item["name"],
                "quantity": money(item["quantity"]),
                "cost": item["cost"],
                "purchase_units": fruit_purchase["units"] if fruit_purchase else None,
                "purchase_unit": fruit_rules[code]["unit"] if fruit_purchase else None,
                "purchase_gross_grams": money(fruit_purchase["gross_grams"])
                if fruit_purchase
                else None,
                "leftover_edible_grams": money(fruit_purchase["leftover_edible_grams"])
                if fruit_purchase
                else None,
                "price_reference": price_records[code].source
                if price_records[code].price_status == "retail_reference"
                else "",
                "price_reference_url": price_records[code].source_url
                if price_records[code].price_status == "retail_reference"
                else "",
            }
        )
    purchase_total = sum(item["cost"] for item in shopping.values())
    rounded_total = round_up_price(purchase_total, 500)
    return protect_plan_instructions(
        {
            "schedule": output_schedule,
            "shopping_groups": [
                {
                    "name": category.replace("_", " ").title(),
                    "items": sorted(items, key=lambda item: item["name"]),
                }
                for category, items in sorted(groups.items())
            ],
            "total": rounded_total,
            "rounding_adjustment": rounded_total - purchase_total,
            "fruit_purchase_estimates": any(code in fruit_rules for code in shopping),
            "estimated_quantities": any(
                meal["estimated_quantities"] for day in output_schedule for meal in day["meals"]
            ),
            "nutrition_proxy_names": sorted(
                {
                    link.ingredient.name
                    for item in selected
                    for link in item["ingredients"]
                    if "ESTIMASI PROKSI" in link.ingredient.calories_method
                }
            ),
            "nutrition_proxies": any(
                "ESTIMASI PROKSI" in link.ingredient.calories_method
                for item in selected
                for link in item["ingredients"]
            ),
            "purchase_yield_estimates": any(
                purchase_grams(link) > Decimal(str(link.quantity))
                for item in selected
                for link in item["ingredients"]
            ),
            "retail_price_references": any(
                price_records[code].price_status == "retail_reference" for code in shopping
            ),
            "nutrition": {
                nutrient: money(value / Decimal(len(schedule) * servings))
                for nutrient, value in nutrition_total.items()
            },
            "protein_floor": money(protein_floor) if protein_floor is not None else None,
            "calorie_cap": money(calorie_cap) if calorie_cap is not None else None,
        }
    )


def build_plan(
    *,
    budget,
    days,
    servings,
    meal_types,
    targets,
    exclude_ingredients,
    allergens=(),
    recent_recipe_codes=(),
    prior_slot_recipes=None,
    fixed_schedule=None,
    seed=None,
    rice="no",
    priority_ingredients=(),
):
    """Return varied halal recipes with a mandatory budget ceiling.

    A 60% spending target and a 2x average menu cap are soft preferences.
    The same seed gives the same plan; callers pass a fresh seed per generate.
    """
    rng = Random(0 if seed is None else seed)
    requested_meals = tuple(meal for meal in MEALS if meal in meal_types)
    if not requested_meals:
        raise ValueError("Pilih minimal satu waktu makan.")
    if not targets or any(target not in TARGET_TAGS for target in targets):
        raise ValueError("Pilih minimal satu target gizi yang tersedia.")
    if "seimbang" in targets and len(set(targets)) > 1:
        raise ValueError("Seimbang tidak bisa digabung dengan target gizi lain.")
    recent_recipe_codes = set(recent_recipe_codes)
    prior_slot_recipes = prior_slot_recipes or {}
    catalog = _load_candidates(
        requested_meals,
        servings,
        exclude_ingredients,
        allergens,
        with_rice=rice_included(rice, servings, targets),
        priority_ingredients=frozenset(priority_ingredients),
    )
    (
        snapshot,
        prices,
        price_records,
        fruit_rules,
        ingredient_purchase_cost,
        candidates,
        matched_terms,
        excluded_names,
    ) = catalog

    missing_meals = [meal for meal in requested_meals if not candidates[meal]]
    available_meals = tuple(meal for meal in requested_meals if candidates[meal])
    if not available_meals:
        requested_labels = ", ".join(MEAL_LABELS[meal].lower() for meal in requested_meals)
        raise ValueError(
            "Belum ada resep siap hitung yang cocok untuk waktu makan: "
            + requested_labels
            + ". Coba kurangi bahan yang dihindari atau lengkapi katalog resep."
        )

    for meal in available_meals:
        candidates[meal].sort(key=lambda item: item["recipe"].pk)
        prior_codes = prior_slot_recipes.get(meal, [])
        if fixed_schedule is None and days == 1 and prior_codes and prior_codes[0]:
            alternatives = [
                item for item in candidates[meal] if item["recipe"].pk != prior_codes[0]
            ]
            if alternatives:
                candidates[meal] = alternatives
    # Search uses a bounded pool; minimum cost and catalog ceiling below still
    # read the full candidate lists.
    cap = meal_cost_cap(budget, days, len(available_meals))

    def search_pools(capped):
        return {
            meal: _candidate_pool(
                [item for item in candidates[meal] if not capped or item["cost"] <= cap]
                or sorted(candidates[meal], key=lambda item: item["cost"])[:days],
                CANDIDATE_POOL_SIZE,
                days,
                rng,
                recent_recipe_codes,
                targets,
            )
            for meal in available_meals
        }

    pools = search_pools(capped=True)

    def minimum_plan_cost(portions, plan_days):
        total = 0
        for meal in available_meals:
            scaled_costs = []
            for item in candidates[meal]:
                recipe_scale = Decimal(portions) / Decimal(item["recipe"].base_servings)
                scaled_costs.append(
                    sum(
                        ingredient_purchase_cost(
                            link.ingredient_id, purchase_grams(link) * recipe_scale
                        )
                        for link in item["ingredients"]
                    )
                )
            scaled_costs.sort()
            if len(scaled_costs) >= plan_days:
                total += sum(scaled_costs[:plan_days])
            else:
                repeats, extras = divmod(plan_days, len(scaled_costs))
                total += repeats * sum(scaled_costs) + sum(scaled_costs[:extras])
        return total

    budget_limit = int(budget // Decimal("500")) * 500
    protein_floor = calorie_cap = None
    if fixed_schedule is not None:
        if len(fixed_schedule) != days:
            raise ValueError("Jumlah hari pada susunan menu tidak cocok.")
        by_code = {
            meal: {item["recipe"].pk: item for item in candidates[meal]} for meal in available_meals
        }
        chosen_by_meal = {meal: [] for meal in available_meals}
        protein_floor, calorie_cap = daily_limits(targets, available_meals)
        for slots in fixed_schedule:
            if set(slots) != set(available_meals):
                raise ValueError("Ketersediaan waktu makan berubah. Buat pratinjau susunan baru.")
            items = []
            for meal in available_meals:
                item = by_code[meal].get(slots[meal])
                if item is None:
                    raise ValueError(
                        "Menu tidak tersedia, melanggar pantangan, atau data harga/gizinya belum lengkap."
                    )
                chosen_by_meal[meal].append(item)
                items.append(item)
            protein = sum((item["nutrition"]["protein"] for item in items), Decimal(0)) / Decimal(
                servings
            )
            calories = sum((item["nutrition"]["calories"] for item in items), Decimal(0)) / Decimal(
                servings
            )
            if (protein_floor is not None and protein < protein_floor) or (
                calorie_cap is not None and calories > calorie_cap
            ):
                raise ValueError(
                    "Menu pengganti tidak memenuhi target gizi harian bersama menu lainnya. Pilih alternatif lain."
                )
        total = sum(item["cost"] for items in chosen_by_meal.values() for item in items)
        feasible = True  # affordability is checked against the whole shopping list below
    elif "tinggi_protein" in targets or "rendah_kalori" in targets:
        nutrition_args = (
            available_meals,
            days,
            servings,
            targets,
            budget_limit,
            recent_recipe_codes,
            prior_slot_recipes,
            rng,
        )
        try:
            total, chosen_by_meal, protein_floor, calorie_cap = _nutrition_plan(
                pools, *nutrition_args
            )
        except ValueError:
            # The per-menu cap is a preference; without it the search either
            # succeeds or reports the real reason (budget or catalog).
            total, chosen_by_meal, protein_floor, calorie_cap = _nutrition_plan(
                search_pools(capped=False), *nutrition_args
            )
        feasible = True
    else:
        preferred = {TARGET_TAGS[target] for target in targets}
        meal_patterns = {
            meal: _recipe_patterns(
                pools[meal],
                days,
                preferred,
                recent_recipe_codes,
                prior_slot_recipes.get(meal, []),
            )
            for meal in available_meals
        }
        # Rounded recipe costs are multiples of Rp100. Bitset shifts find every
        # reachable total without multiplying all meal-group combinations.
        max_catalog_cost = sum(max(meal_patterns[meal]) for meal in available_meals)
        search_limit = min(budget_limit, max_catalog_cost)
        reachable = 1
        mask = (1 << (search_limit // 100 + 1)) - 1
        for meal in available_meals:
            next_reachable = 0
            for group_cost in meal_patterns[meal]:
                next_reachable |= reachable << (group_cost // 100)
            reachable = next_reachable & mask
            if not reachable:
                break

        minimum_cost = sum(min(patterns) for patterns in meal_patterns.values())
        feasible = bool(reachable)
        if feasible:
            best_total = (reachable.bit_length() - 1) * 100
            lowest = spend_floor(budget_limit)
            if best_total < lowest:
                lowest = best_total * (1 - CATALOG_VARIETY_SHARE)
            totals = [
                cost
                for cost in range(ceil(lowest / 100) * 100, best_total + 1, 100)
                if reachable >> (cost // 100) & 1
            ]
            total = rng.choice(totals)
            selected_patterns = _best_patterns_for_total(available_meals, meal_patterns, total)
            chosen_by_meal = _balance_days(
                {
                    meal: _spread(
                        selected_patterns[meal],
                        recent_recipe_codes,
                        prior_slot_recipes.get(meal, []),
                    )
                    for meal in available_meals
                },
                available_meals,
                prior_slot_recipes,
            )
        else:
            total = minimum_cost
            chosen_by_meal = {}
            for meal in available_meals:
                cheapest = meal_patterns[meal][min(meal_patterns[meal])]["items"]
                chosen_by_meal[meal] = _spread(
                    cheapest, recent_recipe_codes, prior_slot_recipes.get(meal, [])
                )

    # Ceiling is the highest spend possible in this catalog while preserving
    # the same anti-repeat rule. It lets the UI explain large unused budgets.
    catalog_ceiling = 0
    for meal in available_meals:
        candidates_sorted = sorted(candidates[meal], key=lambda item: item["cost"], reverse=True)
        if len(candidates_sorted) >= days:
            catalog_ceiling += sum(item["cost"] for item in candidates_sorted[:days])
        else:
            catalog_ceiling += sum(item["cost"] for item in candidates_sorted)
            repeat_cap = max(1, ceil(days / len(candidates_sorted)))
            extra_uses = days - len(candidates_sorted)
            for item in candidates_sorted:
                take = min(repeat_cap - 1, extra_uses)
                catalog_ceiling += take * item["cost"]
                extra_uses -= take
                if extra_uses == 0:
                    break

    min_total = minimum_plan_cost(servings, days)
    feasible_days = [
        option
        for option in range(1, days)
        if round_up_price(minimum_plan_cost(servings, option), 500) <= budget
    ]
    feasible_servings = [
        option
        for option in range(1, servings)
        if round_up_price(minimum_plan_cost(option, days), 500) <= budget
    ]
    required_budget = round_up_price(min_total, 500)

    selected_codes = [
        {meal: chosen_by_meal[meal][day]["recipe"].pk for meal in available_meals}
        for day in range(days)
    ]
    quote = quote_schedule(selected_codes, servings=servings, targets=targets, catalog=catalog)
    schedule, rounded_total = quote["schedule"], quote["total"]

    # Upper estimate only: per-recipe fruit quotes are summed, not shared.
    rounded_ceiling = round_up_price(catalog_ceiling, 500)
    if not feasible and rounded_total <= budget:
        # Several meals can share one fruit purchase. A conservative per-recipe
        # search can reject a plan whose combined shopping quote still fits.
        feasible = True
    required_budget = min(required_budget, rounded_total)
    within_budget = feasible and rounded_total <= budget
    if fixed_schedule is not None:
        required_budget = rounded_total
    return protect_plan_instructions(
        {
            "schedule": schedule,
            "meal_count": len(available_meals),
            "meal_labels": [MEAL_LABELS[meal] for meal in available_meals],
            "missing_meal_labels": [MEAL_LABELS[meal] for meal in missing_meals],
            "excluded_ingredients": sorted(excluded_names),
            "unmatched_exclusions": [
                term for term in exclude_ingredients if term not in matched_terms
            ],
            "planned_recipe_codes": sorted(
                {meal["recipe_code"] for day in schedule for meal in day["meals"]}
            ),
            **quote,
            "difference": (
                max(0, (int(budget) - rounded_total) // 100 * 100)
                if rounded_total <= budget
                else round_up_price(required_budget - int(budget), 100)
            ),
            "within_budget": within_budget,
            "spend_floor": spend_floor(budget),
            "meal_cost_cap": cap,
            "spend_floor_relaxed": within_budget and rounded_total < spend_floor(budget),
            "meal_cost_cap_relaxed": any(
                item["cost"] > cap for items in chosen_by_meal.values() for item in items
            ),
            "preference_notes": budget_preference_notes(schedule, rounded_total, budget),
            "minimum_budget": required_budget,
            "catalog_ceiling": rounded_ceiling,
            "catalog_cannot_use_all_budget": rounded_ceiling < budget,
            "feasible_days": max(feasible_days) if feasible_days else None,
            "feasible_servings": max(feasible_servings) if feasible_servings else None,
            "smallest_scenario_budget": round_up_price(minimum_plan_cost(1, 1), 500),
            "repeated_recipes": len(
                {meal["recipe_code"] for day in schedule for meal in day["meals"]}
            )
            < sum(len(day["meals"]) for day in schedule),
            "region": REGION,
            "snapshot": snapshot,
        }
    )


def replacement_options(
    *,
    budget,
    days,
    servings,
    meal_types,
    targets,
    exclude_ingredients,
    schedule,
    day,
    meal,
    current_total,
    allergens=(),
    rice="no",
):
    """Quote each full alternative schedule using the preview's shopping rules.

    Load the catalog once, not once per alternative. Fruit is pooled across all
    days before buying whole units and rounding the final total.
    """
    requested_meals = tuple(item for item in MEALS if item in meal_types)
    catalog = _load_candidates(
        requested_meals,
        servings,
        exclude_ingredients,
        allergens,
        with_rice=rice_included(rice, servings, targets),
    )
    candidates = catalog[5]
    current_code = schedule[day - 1][meal]
    options = []
    for item in candidates.get(meal, []):
        if item["recipe"].pk == current_code:
            continue
        slots = [dict(slots) for slots in schedule]
        slots[day - 1][meal] = item["recipe"].pk
        try:
            quote = quote_schedule(slots, servings=servings, targets=targets, catalog=catalog)
        except ValueError:
            continue
        if quote["total"] > budget:
            continue
        options.append(
            {
                "recipe_code": item["recipe"].pk,
                "name": item["recipe"].name,
                "delta": int(quote["total"] - Decimal(current_total)),
            }
        )
    return sorted(options, key=lambda option: (option["name"].casefold(), option["recipe_code"]))
