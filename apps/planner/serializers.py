from rest_framework import serializers

from .models import BudgetPlan
from .snapshots import net_total, thaw


class BudgetPlanSerializer(serializers.ModelSerializer):
    """Ringkasan rencana untuk daftar Rencana Saya: judul, status, tanggal, budget, dan total belanja."""

    budget = serializers.CharField(source="inputs.budget")
    total = serializers.SerializerMethodField()

    class Meta:
        model = BudgetPlan
        fields = ["id", "title", "status", "starts_on", "version", "budget", "total", "updated_at"]

    def get_total(self, plan):
        """Uang yang masih perlu dibelanjakan setelah dikurangi stok pantry."""
        return net_total(thaw(plan.snapshot))


class BudgetPlanDetailSerializer(BudgetPlanSerializer):
    """Detail rencana: ringkasan ditambah input planner dan hasil lengkap (jadwal, belanja, gizi)."""

    result = serializers.SerializerMethodField()

    class Meta(BudgetPlanSerializer.Meta):
        fields = [*BudgetPlanSerializer.Meta.fields, "inputs", "result"]

    def get_result(self, plan):
        """Snapshot hasil planner dalam bentuk Decimal/date asli agar dirender sebagai JSON."""
        return thaw(plan.snapshot)
