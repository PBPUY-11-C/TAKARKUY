from rest_framework import serializers

from apps.pantry.models import PantryItem
from apps.planner.models import BudgetPlan
from apps.recipe.models import CookingHistory

from .models import MyRecipe


class MyRecipeSerializer(serializers.ModelSerializer):
    """Resep pribadi beserta bahan dan langkah yang sudah dipecah per baris untuk ditampilkan."""

    daftar_bahan = serializers.ReadOnlyField()
    daftar_langkah = serializers.ReadOnlyField()

    class Meta:
        model = MyRecipe
        fields = [
            "id",
            "nama",
            "waktu_makan",
            "porsi",
            "bahan",
            "langkah",
            "estimasi_harga",
            "daftar_bahan",
            "daftar_langkah",
            "dibuat",
            "diubah",
        ]


class PlanRefSerializer(serializers.ModelSerializer):
    """Identitas singkat rencana (id dan judul), dipakai untuk draf yang belum disimpan."""

    class Meta:
        model = BudgetPlan
        fields = ["id", "title"]


class TodayMealSerializer(serializers.Serializer):
    """Satu menu hari ini dari rencana aktif; nama sudah termasuk makanan pokok tambahan planner."""

    slot_id = serializers.IntegerField(source="pk")
    label = serializers.CharField(source="display_time")
    name = serializers.CharField(source="display_name")
    servings = serializers.IntegerField()
    status = serializers.CharField()


class ActivePlanSerializer(PlanRefSerializer):
    """Rencana aktif hari ini: sisa (atau kelebihan) budget dan menu hari ini."""

    remaining = serializers.ReadOnlyField()
    over_budget = serializers.BooleanField()
    today_meals = TodayMealSerializer(many=True)

    class Meta(PlanRefSerializer.Meta):
        fields = [*PlanRefSerializer.Meta.fields, "remaining", "over_budget", "today_meals"]


class WeekMealSerializer(serializers.Serializer):
    """Satu menu terjadwal pada 7 hari ke depan."""

    slot_id = serializers.IntegerField()
    plan_title = serializers.CharField()
    label = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()


class WeekDaySerializer(serializers.Serializer):
    """Tanggal dan daftar menu pada hari itu."""

    date = serializers.DateField()
    meals = WeekMealSerializer(many=True)


class StockBatchSerializer(serializers.ModelSerializer):
    """Batch pantry prioritas; days_left None bila tanggal kedaluwarsa belum diketahui."""

    days_left = serializers.IntegerField(allow_null=True)

    class Meta:
        model = PantryItem
        fields = [
            "id",
            "name",
            "quantity",
            "unit",
            "expiry_source",
            "estimated_expires_on",
            "days_left",
        ]


class StockGroupsSerializer(serializers.Serializer):
    """Batch prioritas per grup (maks 3 per grup): segera habis, tanggal belum diketahui, lewat tanggal."""

    soon = StockBatchSerializer(many=True)
    unknown = StockBatchSerializer(many=True)
    expired = StockBatchSerializer(many=True)


class RecentCookingSerializer(serializers.ModelSerializer):
    """Riwayat masak terbaru; recipe bernilai null bila resep katalog sudah dihapus."""

    class Meta:
        model = CookingHistory
        fields = ["id", "recipe", "recipe_name", "servings", "cooked_at"]


class DashboardSerializer(serializers.Serializer):
    """Ringkasan dashboard dari dashboard_data ditambah jumlah resep pribadi."""

    today = serializers.DateField()
    plans = ActivePlanSerializer(many=True)
    week = WeekDaySerializer(many=True)
    week_has_meals = serializers.BooleanField()
    unsaved_draft = PlanRefSerializer(allow_null=True)
    stock_counts = serializers.DictField(child=serializers.IntegerField())
    stock_groups = StockGroupsSerializer()
    cooking_count = serializers.IntegerField()
    recent_cooking = RecentCookingSerializer(many=True)
    my_recipe_count = serializers.IntegerField()
