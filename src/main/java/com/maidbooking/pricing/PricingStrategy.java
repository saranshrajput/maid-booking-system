package com.maidbooking.pricing;

import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import java.math.BigDecimal;

public interface PricingStrategy {
    BigDecimal price(Maid maid, ServiceType serviceType, TimeSlot slot);
}
