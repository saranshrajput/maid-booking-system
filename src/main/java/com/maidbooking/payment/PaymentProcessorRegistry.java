package com.maidbooking.payment;

import com.maidbooking.domain.PaymentMethodType;
import com.maidbooking.exception.InvalidRequestException;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class PaymentProcessorRegistry {
    private final Map<PaymentMethodType, PaymentProcessor> processors = new EnumMap<>(PaymentMethodType.class);

    public PaymentProcessorRegistry(List<PaymentProcessor> all) {
        all.forEach(p -> processors.put(p.method(), p));
    }

    public PaymentProcessor get(PaymentMethodType method) {
        PaymentProcessor processor = processors.get(method);
        if (processor == null) throw new InvalidRequestException("Unsupported payment method: " + method);
        return processor;
    }
}
