package com.unlockops.grant.model;

import java.math.BigDecimal;

public record DepartmentBudget(BigDecimal remainingMonthlyAmount, BigDecimal unitMonthlyPrice) {
    public boolean canAffordSeat() { return remainingMonthlyAmount.compareTo(unitMonthlyPrice) >= 0; }
}
