package com.maidbooking.pricing;

import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

@Component
public class HourlyPricingStrategy implements PricingStrategy {

    @Override
    public BigDecimal price(Maid maid, ServiceType serviceType, TimeSlot slot) {
        return maid.rateFor(serviceType)
                .multiply(BigDecimal.valueOf(slot.minutes()))
                .divide(BigDecimal.valueOf(60), 2, RoundingMode.HALF_UP);
    }
}
