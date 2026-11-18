from rest_framework import serializers

from .models import PantryItem, PantryMovement


class PantryItemSerializer(serializers.ModelSerializer):
    """Satu batch stok untuk daftar pantry: jumlah, lokasi, kedaluwarsa, konversi, dan version."""

    ingredient_code = serializers.CharField(source="ingredient_id", allow_null=True)

    class Meta:
        model = PantryItem
        fields = [
            "id",
            "name",
            "category",
            "quantity",
            "unit",
            "location",
            "ingredient_code",
            "starting_on",
            "shelf_life_days",
            "estimated_expires_on",
            "expiry_source",
            "source",
            "base_unit",
            "pack_weight_g",
            "grams_per_unit",
            "conversion_note",
            "archived_at",
            "version",
            "added_at",
            "updated_at",
        ]


class PantryMovementSerializer(serializers.ModelSerializer):
    """Satu baris riwayat stok dengan format yang sama seperti endpoint riwayat web."""

    kind = serializers.CharField(source="get_kind_display")
    before = serializers.DecimalField(source="quantity_before", max_digits=14, decimal_places=6)
    after = serializers.DecimalField(source="quantity_after", max_digits=14, decimal_places=6)

    class Meta:
        model = PantryMovement
        fields = ["kind", "before", "after", "created_at", "snapshot"]


class PantryItemDetailSerializer(PantryItemSerializer):
    """Detail batch ditambah maksimal 100 riwayat terbaru, sama dengan batas di web."""

    movements = serializers.SerializerMethodField()

    class Meta(PantryItemSerializer.Meta):
        fields = [*PantryItemSerializer.Meta.fields, "movements"]

    def get_movements(self, item):
        """Riwayat movement item, terbaru lebih dulu."""
        return PantryMovementSerializer(item.movements.order_by("-pk")[:100], many=True).data
