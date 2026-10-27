package com.maidbooking.domain;

import com.maidbooking.exception.InvalidRequestException;
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class Maid {
    private final String id;
    private final String name;
    private final String locality;
    private final Gender gender;
    private final double rating;
    private final Map<ServiceType, BigDecimal> hourlyRates;
    private final Set<String> skills;
    private final List<AvailabilityWindow> availability;

    public Maid(String id, String name, String locality, Gender gender, double rating,
                Map<ServiceType, BigDecimal> hourlyRates, Set<String> skills,
                List<AvailabilityWindow> availability) {
        if (name == null || name.isBlank()) throw new InvalidRequestException("Maid name is required");
        if (locality == null || locality.isBlank()) throw new InvalidRequestException("Maid locality is required");
        if (gender == null) throw new InvalidRequestException("Maid gender is required");
        if (rating < 0 || rating > 5) throw new InvalidRequestException("Rating must be between 0 and 5");
        if (hourlyRates == null || hourlyRates.isEmpty()) {
            throw new InvalidRequestException("Maid must offer at least one service with a rate");
        }
        if (hourlyRates.values().stream().anyMatch(r -> r == null || r.signum() <= 0)) {
            throw new InvalidRequestException("Hourly rates must be positive");
        }
        if (availability == null || availability.isEmpty()) {
            throw new InvalidRequestException("Maid must have at least one availability window");
        }
        this.id = id;
        this.name = name.trim();
        this.locality = locality.trim();
        this.gender = gender;
        this.rating = rating;
        this.hourlyRates = Map.copyOf(hourlyRates);
        this.skills = skills == null ? Set.of() : skills.stream()
                .map(s -> s.trim().toLowerCase(Locale.ROOT)).collect(Collectors.toUnmodifiableSet());
        this.availability = List.copyOf(availability);
    }

    public boolean offers(ServiceType type) {
        return hourlyRates.containsKey(type);
    }

    public boolean servesLocality(String requested) {
        return locality.equalsIgnoreCase(requested.trim());
    }

    public boolean hasSkills(Set<String> required) {
        return skills.containsAll(required.stream().map(s -> s.trim().toLowerCase(Locale.ROOT)).toList());
    }

    public boolean worksDuring(TimeSlot slot) {
        return availability.stream().anyMatch(w -> w.covers(slot));
    }

    public BigDecimal rateFor(ServiceType type) {
        BigDecimal rate = hourlyRates.get(type);
        if (rate == null) throw new InvalidRequestException(name + " does not offer " + type);
        return rate;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getLocality() { return locality; }
    public Gender getGender() { return gender; }
    public double getRating() { return rating; }
    public Map<ServiceType, BigDecimal> getHourlyRates() { return hourlyRates; }
    public Set<String> getSkills() { return skills; }
    public List<AvailabilityWindow> getAvailability() { return availability; }
}
