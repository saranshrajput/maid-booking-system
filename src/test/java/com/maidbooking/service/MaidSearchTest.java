package com.maidbooking.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.maidbooking.domain.Gender;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.search.MaidSearchCriteria;
import com.maidbooking.search.MaidSearchService;
import com.maidbooking.search.StandardFilterProviders;
import com.maidbooking.support.TestContext;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MaidSearchTest {
    private TestContext ctx;
    private MaidSearchService search;
    private Maid asha;
    private Maid bina;
    private Maid chitra;

    @BeforeEach
    void setUp() {
        ctx = new TestContext();
        StandardFilterProviders f = new StandardFilterProviders();
        search = new MaidSearchService(ctx.maidRepository, List.of(f.localityFilter(), f.serviceTypeFilter(),
                f.ratingFilter(), f.priceFilter(), f.genderFilter(), f.skillsFilter(),
                f.availabilityFilter(ctx.availabilityService)));
        asha = ctx.maid("Asha", "Koramangala", Gender.FEMALE, 4.8, new BigDecimal("250"), "deep-cleaning");
        bina = ctx.maid("Bina", "Koramangala", Gender.FEMALE, 4.0, new BigDecimal("150"));
        chitra = ctx.maid("Chitra", "Indiranagar", Gender.MALE, 4.5, new BigDecimal("200"), "deep-cleaning");
    }

    private MaidSearchCriteria criteria(String locality, TimeSlot slot, Double minRating, BigDecimal maxRate,
                                        Gender gender, Set<String> skills) {
        return new MaidSearchCriteria(locality, ServiceType.CLEANING, slot, minRating, maxRate, gender, skills);
    }

    @Test
    void noCriteriaReturnsEveryoneSortedByRating() {
        List<Maid> result = search.search(new MaidSearchCriteria(null, null, null, null, null, null, null));
        assertEquals(List.of("Asha", "Chitra", "Bina"), result.stream().map(Maid::getName).toList());
    }

    @Test
    void filtersCombine() {
        assertEquals(List.of(asha), search.search(criteria("koramangala", null, 4.5, null, null, null)));
        assertEquals(List.of(bina), search.search(criteria("Koramangala", null, null, new BigDecimal("200"), null, null)));
        assertEquals(List.of(chitra), search.search(criteria(null, null, null, null, Gender.MALE, null)));
        assertEquals(List.of(chitra, asha).size(), search.search(criteria(null, null, null, null, null, Set.of("Deep-Cleaning"))).size());
    }

    @Test
    void onlyAvailableMaidsAreReturnedForTheRequestedSlot() {
        LocalDateTime start = LocalDateTime.of(2030, 1, 8, 10, 0);
        ctx.bookScheduled(asha, start, 60);

        List<Maid> result = search.search(criteria("Koramangala", TimeSlot.of(start.plusMinutes(30), 60), null, null, null, null));
        assertEquals(List.of(bina), result);
    }

    @Test
    void maidsOutsideWorkingHoursAreExcluded() {
        TimeSlot night = TimeSlot.of(LocalDateTime.of(2030, 1, 8, 22, 0), 60);
        assertEquals(0, search.search(criteria(null, night, null, null, null, null)).size());
    }

    @Test
    void onboardingValidatesProfile() {
        assertThrows(InvalidRequestException.class,
                () -> ctx.maid("", "Koramangala", Gender.FEMALE, 4.0, new BigDecimal("100")));
        assertThrows(InvalidRequestException.class,
                () -> ctx.maid("X", "Koramangala", Gender.FEMALE, 7.0, new BigDecimal("100")));
        assertThrows(InvalidRequestException.class,
                () -> ctx.maid("X", "Koramangala", Gender.FEMALE, 4.0, new BigDecimal("-5")));
    }
}
