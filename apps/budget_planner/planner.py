"""Deterministic planner over the curated local recipe and price catalog."""

from collections import Counter, defaultdict
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from itertools import combinations_with_replacement, product
from heapq import nsmallest
from math import ceil

from apps.catalog.models import IngredientPrice, Recipe


REGION = "Kabupaten Garut"
MEALS = ("sarapan", "makan_siang", "makan_malam")
MEAL_LABELS = {"sarapan": "Pagi", "makan_siang": "Siang", "makan_malam": "Malam"}
TARGET_TAGS = {
    "seimbang": "seimbang_internal",
    "tinggi_protein": "tinggi_protein",
    "rendah_kalori": "rendah_kalori",
}
NUTRIENTS = ("calories", "protein", "carbs", "fat")
MAX_BUDGET_GAP = 50000
TARGET_BUDGET_GAP_RATIO = Decimal("0.20")
MAX_TIE_BREAK_CHECKS = 300000
NUTRITION_BEAM_WIDTH = 5
HIGH_PROTEIN_GRAMS_PER_DAY = Decimal("80")
CALORIE_LIMITS_BY_MEAL = {
    "sarapan": Decimal("500"),
    "makan_siang": Decimal("325"),
    "makan_malam": Decimal("325"),
}


def money(value):
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_up_price(value, multiple):
    """Round a rupiah estimate up to the next Rp100 or Rp500."""
    return int((Decimal(value) / Decimal(multiple)).to_integral_value(rounding=ROUND_CEILING) * multiple)


def budget_target_minimum(budget):
    """Allow up to 20% unused budget, capped at Rp50,000."""
    allowed_gap = min(MAX_BUDGET_GAP, int(Decimal(budget) * TARGET_BUDGET_GAP_RATIO))
    return max(0, int(budget) - allowed_gap)


def _recipe_patterns(candidates, slots, preferred_tags, recent_codes, prior_slot_codes=()):
    """Find each reachable meal cost without enumerating recipe combinations."""
    max_uses = max(1, ceil(slots / len(candidates)))
    patterns_by_cost = {}
    if len(candidates) >= slots:
        # The cost of each ingredient is rounded to Rp100, so many different
        # recipe sets have the same total. Keep the best set for each count/cost.
        # Each candidate enters once, which also prevents repeat menus.
        states = [{} for _ in range(slots + 1)]
        states[0][0] = ((), 0, 0, 0, 0)  # indexes, all-target hits, total hits, recent hits, prior hits
        prior_codes = set(prior_slot_codes)
        for index, item in enumerate(candidates):
            code = item["recipe"].pk
            for count in range(min(slots, index + 1), 0, -1):
                for cost, (indexes, all_hits, target_hits, recent_hits, prior_hits) in states[count - 1].items():
                    new_cost = cost + item["cost"]
                    matched = len(preferred_tags & item["tags"])
                    candidate = (
                        (*indexes, index),
                        all_hits + (matched == len(preferred_tags)),
                        target_hits + matched,
                        recent_hits + (code in recent_codes),
                        prior_hits + (code in prior_codes),
                    )
                    old = states[count].get(new_cost)
                    if old is None or (-candidate[4], candidate[1], candidate[2], -candidate[3]) > (
                        -old[4], old[1], old[2], -old[3]
                    ):
                        states[count][new_cost] = candidate
        patterns = (tuple(candidates[index] for index in state[0])
                    for state in states[slots].values())
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
        spread = _spread(pattern, recent_codes, prior_slot_codes)
        pattern_score = (
            -sum(1 for index, item in enumerate(spread)
                 if index < len(prior_slot_codes) and prior_slot_codes[index] == item["recipe"].pk),
            sum(preferred_tags <= item["tags"] for item in pattern),
            sum(len(preferred_tags & item["tags"]) for item in pattern),
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
        selected = min(available, key=lambda code: (
            code == old_code,
            code in recent_codes,
            by_code[code]["cost"],
            code,
        ))
        result.append(by_code[selected])
        counts[selected] -= 1
    return result


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
            rank = tuple(first["score"][i] + second["score"][i] for i in range(5))
            if best_rank is None or rank > best_rank:
                best_rank, best_choice = rank, (first, second)
    else:
        last_group = groups[2]
        upper_rank = tuple(sum(max(pattern["score"][i] for pattern in group.values())
                               for group in groups) for i in range(5))
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
                rank = tuple(first["score"][i] + second["score"][i] + third["score"][i]
                             for i in range(5))
                if best_rank is None or rank > best_rank:
                    best_rank, best_choice = rank, (first, second, third)
                    if rank == upper_rank:
                        return {meal: choice["items"] for meal, choice in zip(meals, best_choice)}
    return {meal: choice["items"] for meal, choice in zip(meals, best_choice)}


def _nutrition_plan(candidates, meals, days, servings, targets, budget_limit,
                    recent_codes, prior_slot_recipes):
    """Choose affordable day bundles; nutritional limits apply to each whole day."""
    protein_floor = ((HIGH_PROTEIN_GRAMS_PER_DAY * len(meals) / Decimal(len(MEALS)))
                     .quantize(Decimal("1"), rounding=ROUND_CEILING)
                     if "tinggi_protein" in targets else None)
    calorie_cap = (sum((CALORIE_LIMITS_BY_MEAL[meal] for meal in meals), Decimal(0))
                   if "rendah_kalori" in targets else None)
    bundles = []
    for items in product(*(candidates[meal] for meal in meals)):
        protein = sum((item["nutrition"]["protein"] / Decimal(servings) for item in items), Decimal(0))
        calories = sum((item["nutrition"]["calories"] / Decimal(servings) for item in items), Decimal(0))
        if protein_floor is not None and protein < protein_floor:
            continue
        if calorie_cap is not None and calories > calorie_cap:
            continue
        bundles.append((sum(item["cost"] for item in items), items))
    if not bundles:
        conditions = []
        if protein_floor is not None:
            conditions.append(f"minimal {money(protein_floor)} g protein")
        if calorie_cap is not None:
            conditions.append(f"maksimal {money(calorie_cap)} kkal")
        raise ValueError(
            "Belum ada kombinasi menu yang memenuhi " + " dan ".join(conditions)
            + " per orang untuk waktu makan yang dipilih. Coba tambah variasi resep atau ubah pilihan waktu makan/pantangan."
        )

    bundles.sort(key=lambda bundle: bundle[0])
    eligible_codes = {
        meal: {items[index]["recipe"].pk for _, items in bundles}
        for index, meal in enumerate(meals)
    }
    repeat_caps = {meal: max(1, ceil(days / len(eligible_codes[meal]))) for meal in meals}
    min_daily_cost = bundles[0][0]
    if round_up_price(min_daily_cost * days, 500) > budget_limit:
        raise ValueError(
            f"Budget belum cukup untuk target gizi ini. Perkiraan batas bawah biaya "
            f"{days} hari adalah Rp {round_up_price(min_daily_cost * days, 500):,}.".replace(",", ".")
        )

    # A small beam preserves affordable alternatives when a high-cost choice
    # would consume the budget or repeat a recipe needed on later days.
    states = [(0, (), Counter())]
    for day in range(days):
        next_states = []
        remaining_days = days - day - 1
        for spent, selected, uses in states:
            remaining_budget = budget_limit - spent - remaining_days * min_daily_cost
            target_cost = (budget_limit - spent) / (remaining_days + 1)
            def rank_options(enforce_repeat_cap):
                ranked = []
                for cost, items in bundles:
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
                    rank = (abs(cost - target_cost), repeats, prior_hits, recent_hits, -cost, codes)
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
        next_states.sort(key=lambda state: (
            abs(state[0] - budget_limit * (day + 1) / days),
            sum(max(0, count - 1) for count in state[2].values()),
            -state[0],
        ))
        states = next_states[:NUTRITION_BEAM_WIDTH]
    spent, selected, _ = max(states, key=lambda state: (
        state[0], -sum(max(0, count - 1) for count in state[2].values())
    ))
    return spent, {meal: [day_items[index] for day_items in selected]
                   for index, meal in enumerate(meals)}, protein_floor, calorie_cap


def build_plan(*, budget, days, servings, meal_types, targets, exclude_ingredients,
               recent_recipe_codes=(), prior_slot_recipes=None):
    """Return the highest affordable total with varied recipes."""
    requested_meals = tuple(meal for meal in MEALS if meal in meal_types)
    if not requested_meals:
        raise ValueError("Pilih minimal satu waktu makan.")
    if not targets or any(target not in TARGET_TAGS for target in targets):
        raise ValueError("Pilih minimal satu target gizi yang tersedia.")
    if "seimbang" in targets and len(set(targets)) > 1:
        raise ValueError("Seimbang tidak bisa digabung dengan target gizi lain.")
    recent_recipe_codes = set(recent_recipe_codes)
    prior_slot_recipes = prior_slot_recipes or {}
    snapshot = (
        IngredientPrice.objects.filter(region=REGION, price_status="published", unit="kg")
        .order_by("-recorded_at").values_list("recorded_at", flat=True).first()
    )
    if snapshot is None:
        raise ValueError("Data harga Kabupaten Garut belum tersedia. Impor katalog lebih dulu.")

    prices = {}
    for price in IngredientPrice.objects.filter(
        region=REGION, recorded_at=snapshot, price_status="published", unit="kg"
    ):
        prices[price.ingredient_id] = Decimal(price.price_rupiah) / Decimal(str(price.quantity))

    candidates = defaultdict(list)
    matched_terms, excluded_names = set(), set()
    recipes = Recipe.objects.filter(is_active=True, is_plannable=True).prefetch_related(
        "recipeingredient_set__ingredient", "recipetag_set"
    )
    for recipe in recipes:
        if not recipe.base_servings or recipe.meal_type not in requested_meals:
            continue
        tags = {tag.tag for tag in recipe.recipetag_set.all()}
        ingredients = list(recipe.recipeingredient_set.all())
        if any(
            term in link.ingredient.name.casefold()
            for link in ingredients for term in exclude_ingredients
        ):
            for link in ingredients:
                for term in exclude_ingredients:
                    if term in link.ingredient.name.casefold():
                        matched_terms.add(term)
                        excluded_names.add(link.ingredient.name)
            continue
        if not ingredients or any(
            link.unit != "g" or link.quantity is None or link.quantity <= 0
            or link.ingredient_id not in prices
            or any(getattr(link.ingredient, f"{nutrient}_per_100g") is None for nutrient in NUTRIENTS)
            for link in ingredients
        ):
            continue

        scale = Decimal(servings) / Decimal(recipe.base_servings)
        ingredient_costs = {
            link.recipe_ingredient_code: round_up_price(
                Decimal(str(link.quantity)) * scale * prices[link.ingredient_id] / Decimal("1000"), 100
            )
            for link in ingredients
        }
        nutrition = {
            nutrient: sum((
                Decimal(str(link.quantity)) * scale
                * Decimal(str(getattr(link.ingredient, f"{nutrient}_per_100g"))) / Decimal("100")
                for link in ingredients
            ), Decimal("0"))
            for nutrient in NUTRIENTS
        }
        candidates[recipe.meal_type].append({
            "recipe": recipe, "tags": tags, "ingredients": ingredients,
            "ingredient_costs": ingredient_costs, "scale": scale,
            "cost": sum(ingredient_costs.values()), "nutrition": nutrition,
        })

    missing_meals = [meal for meal in requested_meals if not candidates[meal]]
    available_meals = tuple(meal for meal in requested_meals if candidates[meal])
    if not available_meals:
        requested_labels = ", ".join(MEAL_LABELS[meal].lower() for meal in requested_meals)
        raise ValueError(
            "Belum ada resep siap hitung yang cocok untuk waktu makan: " + requested_labels
            + ". Coba kurangi bahan yang dihindari atau lengkapi katalog resep."
        )

    for meal in available_meals:
        candidates[meal].sort(key=lambda item: item["recipe"].pk)
        prior_codes = prior_slot_recipes.get(meal, [])
        if days == 1 and prior_codes and prior_codes[0]:
            alternatives = [item for item in candidates[meal]
                            if item["recipe"].pk != prior_codes[0]]
            if alternatives:
                candidates[meal] = alternatives

    def minimum_plan_cost(portions, plan_days):
        total = 0
        for meal in available_meals:
            scaled_costs = []
            for item in candidates[meal]:
                recipe_scale = Decimal(portions) / Decimal(item["recipe"].base_servings)
                scaled_costs.append(sum(round_up_price(
                    Decimal(str(link.quantity)) * recipe_scale * prices[link.ingredient_id] / Decimal("1000"), 100
                ) for link in item["ingredients"]))
            scaled_costs.sort()
            if len(scaled_costs) >= plan_days:
                total += sum(scaled_costs[:plan_days])
            else:
                repeats, extras = divmod(plan_days, len(scaled_costs))
                total += repeats * sum(scaled_costs) + sum(scaled_costs[:extras])
        return total

    budget_limit = int(budget // Decimal("500")) * 500
    protein_floor = calorie_cap = None
    if "tinggi_protein" in targets or "rendah_kalori" in targets:
        total, chosen_by_meal, protein_floor, calorie_cap = _nutrition_plan(
            candidates, available_meals, days, servings, targets, budget_limit,
            recent_recipe_codes, prior_slot_recipes,
        )
        feasible = True
    else:
        preferred = {TARGET_TAGS[target] for target in targets}
        meal_patterns = {
            meal: _recipe_patterns(
                candidates[meal], days, preferred, recent_recipe_codes, prior_slot_recipes.get(meal, [])
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
            total = (reachable.bit_length() - 1) * 100
            selected_patterns = _best_patterns_for_total(available_meals, meal_patterns, total)
            chosen_by_meal = {
                meal: _spread(selected_patterns[meal], recent_recipe_codes, prior_slot_recipes.get(meal, []))
                for meal in available_meals
            }
        else:
            total = minimum_cost
            chosen_by_meal = {}
            for meal in available_meals:
                cheapest = meal_patterns[meal][min(meal_patterns[meal])]["items"]
                chosen_by_meal[meal] = _spread(cheapest, recent_recipe_codes, prior_slot_recipes.get(meal, []))

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
        option for option in range(1, days)
        if round_up_price(minimum_plan_cost(servings, option), 500) <= budget
    ]
    feasible_servings = [
        option for option in range(1, servings)
        if round_up_price(minimum_plan_cost(option, days), 500) <= budget
    ]
    required_budget = round_up_price(min_total, 500)

    shopping = {}
    nutrition_total = {nutrient: Decimal("0") for nutrient in NUTRIENTS}
    schedule = []
    for day in range(days):
        meals = []
        day_nutrition = {nutrient: Decimal("0") for nutrient in NUTRIENTS}
        for meal in available_meals:
            item = chosen_by_meal[meal][day]
            for nutrient in NUTRIENTS:
                nutrition_total[nutrient] += item["nutrition"][nutrient]
                day_nutrition[nutrient] += item["nutrition"][nutrient]
            for link in item["ingredients"]:
                code = link.ingredient_id
                if code not in shopping:
                    shopping[code] = {"name": link.ingredient.name,
                                      "category": "sayur" if code == "ING-KUBIS" else link.ingredient.category,
                                      "quantity": Decimal("0"), "cost": 0}
                shopping[code]["quantity"] += Decimal(str(link.quantity)) * item["scale"]
                shopping[code]["cost"] += item["ingredient_costs"][link.recipe_ingredient_code]
            meals.append({"type": meal, "label": MEAL_LABELS[meal], "recipe_code": item["recipe"].pk,
                          "name": item["recipe"].name, "cost": item["cost"],
                          "calories": money(item["nutrition"]["calories"] / Decimal(servings))})
        schedule.append({"number": day + 1, "meals": meals,
                         "protein": money(day_nutrition["protein"] / Decimal(servings)),
                         "calories": money(day_nutrition["calories"] / Decimal(servings))})

    groups = defaultdict(list)
    for item in shopping.values():
        groups[item["category"]].append({"name": item["name"], "quantity": money(item["quantity"]), "cost": item["cost"]})
    shopping_groups = [
        {"name": category.replace("_", " ").title(), "items": sorted(items, key=lambda item: item["name"])}
        for category, items in sorted(groups.items())
    ]

    rounded_total = round_up_price(total, 500)
    rounded_ceiling = round_up_price(catalog_ceiling, 500)
    target_minimum = budget_target_minimum(budget)
    within_budget = feasible and rounded_total <= budget
    return {
        "schedule": schedule,
        "meal_count": len(available_meals),
        "meal_labels": [MEAL_LABELS[meal] for meal in available_meals],
        "missing_meal_labels": [MEAL_LABELS[meal] for meal in missing_meals],
        "excluded_ingredients": sorted(excluded_names),
        "unmatched_exclusions": [term for term in exclude_ingredients if term not in matched_terms],
        "planned_recipe_codes": sorted({meal["recipe_code"] for day in schedule for meal in day["meals"]}),
        "shopping_groups": shopping_groups,
        "total": rounded_total,
        "rounding_adjustment": rounded_total - total,
        "difference": (
            max(0, (int(budget) - rounded_total) // 100 * 100)
            if rounded_total <= budget
            else round_up_price(required_budget - int(budget), 100)
        ),
        "within_budget": within_budget,
        "within_target_range": within_budget and rounded_total >= target_minimum,
        "target_minimum": target_minimum,
        "catalog_below_target": rounded_ceiling < target_minimum,
        "minimum_budget": required_budget,
        "catalog_ceiling": rounded_ceiling,
        "catalog_cannot_use_all_budget": rounded_ceiling < budget,
        "feasible_days": max(feasible_days) if feasible_days else None,
        "feasible_servings": max(feasible_servings) if feasible_servings else None,
        "smallest_scenario_budget": round_up_price(minimum_plan_cost(1, 1), 500),
        "nutrition": {
            "calories": money(nutrition_total["calories"] / Decimal(days * servings)),
            "protein": money(nutrition_total["protein"] / Decimal(days * servings)),
            "carbs": money(nutrition_total["carbs"] / Decimal(days * servings)),
            "fat": money(nutrition_total["fat"] / Decimal(days * servings)),
        },
        "protein_floor": money(protein_floor) if protein_floor is not None else None,
        "calorie_cap": money(calorie_cap) if calorie_cap is not None else None,
        "repeated_recipes": len({meal["recipe_code"] for day in schedule for meal in day["meals"]}) < sum(
            len(day["meals"]) for day in schedule
        ),
        "region": REGION,
        "snapshot": snapshot,
    }
