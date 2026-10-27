package com.maidbooking.service;

import com.maidbooking.domain.AvailabilityWindow;
import com.maidbooking.domain.Gender;
import com.maidbooking.domain.ServiceType;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Set;

public record OnboardMaidCommand(String name, String locality, Gender gender, double rating,
                                 Map<ServiceType, BigDecimal> hourlyRates, Set<String> skills,
                                 List<AvailabilityWindow> availability) {
}
