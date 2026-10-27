package com.maidbooking.search;

import com.maidbooking.service.AvailabilityService;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StandardFilterProviders {

    @Bean
    public MaidFilterProvider localityFilter() {
        return c -> Optional.ofNullable(c.locality()).filter(l -> !l.isBlank()).map(l -> m -> m.servesLocality(l));
    }

    @Bean
    public MaidFilterProvider serviceTypeFilter() {
        return c -> Optional.ofNullable(c.serviceType()).map(t -> m -> m.offers(t));
    }

    @Bean
    public MaidFilterProvider ratingFilter() {
        return c -> Optional.ofNullable(c.minRating()).map(min -> m -> m.getRating() >= min);
    }

    // With a service type the cap applies to that service's rate, otherwise to any offered rate.
    @Bean
    public MaidFilterProvider priceFilter() {
        return c -> Optional.ofNullable(c.maxHourlyRate()).map(max -> m -> c.serviceType() != null
                ? m.offers(c.serviceType()) && m.rateFor(c.serviceType()).compareTo(max) <= 0
                : m.getHourlyRates().values().stream().anyMatch(r -> r.compareTo(max) <= 0));
    }

    @Bean
    public MaidFilterProvider genderFilter() {
        return c -> Optional.ofNullable(c.gender()).map(g -> m -> m.getGender() == g);
    }

    @Bean
    public MaidFilterProvider skillsFilter() {
        return c -> Optional.ofNullable(c.skills()).filter(s -> !s.isEmpty()).map(s -> m -> m.hasSkills(s));
    }

    @Bean
    public MaidFilterProvider availabilityFilter(AvailabilityService availabilityService) {
        return c -> Optional.ofNullable(c.requestedSlot()).map(slot -> m -> availabilityService.isAvailable(m, slot));
    }
}
